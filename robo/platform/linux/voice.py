"""Robo's voices on Linux.

    nice Robo   a soft, natural Piper voice (tts_worker.py, in Robo's venv),
                lifted a little in pitch so it sounds cute
    evil Robo   espeak-ng through its C library, deep and buzzy, with the
                robot filter from robo.audio ("bwoo-woo")

LinuxVoice picks per sentence via `style` ('normal' or 'evil'). If Piper
isn't installed, the nice voice falls back to a gentle espeak-ng voice.
SpdSayVoice is a last resort that uses the plain system voice.
"""
import ctypes
import ctypes.util
import itertools
import json
import logging
import os
import random
import shutil
import signal
import subprocess
import tempfile
import threading

from gi.repository import GLib

from robo import audio
from robo.platform.base import SpeechOutput, Utterance

from .paths import find_voice, venv_python

log = logging.getLogger(__name__)

TTS_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tts_worker.py')
FRAME = 1 / 30
PLAYBACK_LATENCY_FRAMES = 3   # the player needs a moment to start
BASE_WPM = 165

ESPEAK_NICE = 'en-us+f4'      # fallback nice voice
ESPEAK_EVIL = 'en-us+m3'      # evil robot: deep and gravelly
EVIL_PITCH = 22


def nice_pitch_factor(voice_pitch):
    """Settings pitch 0..99 -> playback speed-up for the soft voice (0.88..1.15)."""
    return 0.88 + max(0.0, min(99.0, voice_pitch)) / 99 * 0.27


# ---------------------------------------------------------------- espeak-ng
AUDIO_OUTPUT_SYNCHRONOUS = 2
POS_CHARACTER = 1
CHARS_UTF8, END_PAUSE = 0x1, 0x1000
P_RATE, P_VOLUME, P_PITCH, P_RANGE = 1, 2, 3, 4
SYNTH_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int,
                                  ctypes.c_void_p)


class Espeak:
    """Minimal binding to libespeak-ng: synthesise text into samples."""

    def __init__(self):
        name = ctypes.util.find_library('espeak-ng') or 'libespeak-ng.so.1'
        lib = self.lib = ctypes.CDLL(name)
        lib.espeak_Initialize.restype = ctypes.c_int
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p,
                                          ctypes.c_int]
        lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.espeak_Synth.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
                                     ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_void_p]
        self.rate = lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, None, 0)
        if self.rate <= 0:
            raise OSError('espeak-ng could not start')
        self._samples = None
        self._callback = SYNTH_CALLBACK(self._collect)    # keep a reference!
        lib.espeak_SetSynthCallback(self._callback)
        self._lock = threading.Lock()

    def _collect(self, wav, n, _events):
        if n > 0 and wav:
            self._samples.extend(ctypes.cast(wav, ctypes.POINTER(ctypes.c_short * n)).contents)
        return 0

    def synth(self, text, voice=ESPEAK_NICE, wpm=BASE_WPM, pitch=75):
        import array
        with self._lock:
            self._samples = array.array('h')
            self.lib.espeak_SetVoiceByName(voice.encode())
            self.lib.espeak_SetParameter(P_RATE, int(wpm), 0)
            self.lib.espeak_SetParameter(P_PITCH, int(pitch), 0)
            self.lib.espeak_SetParameter(P_RANGE, 70, 0)
            data = text.encode('utf-8')
            self.lib.espeak_Synth(data, len(data) + 1, 0, POS_CHARACTER, 0,
                                  CHARS_UTF8 | END_PAUSE, None, None)
            self.lib.espeak_Synchronize()
            samples, self._samples = self._samples, None
        return samples


# ---------------------------------------------------------------- Piper
class Piper:
    """Talks to tts_worker.py. Calls block, so use them from a background thread."""

    def __init__(self, python=None, model=None):
        self.python = python or venv_python()
        self.model = model or find_voice()
        self.available = bool(self.model) and os.path.exists(self.python)
        self.proc = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def _ensure(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        self.proc = subprocess.Popen([self.python, '-I', TTS_WORKER, '--model', self.model],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        ready = self._read()
        if not ready or ready.get('event') != 'ready':
            log.warning('soft voice failed to start: %s', ready and ready.get('text'))
            self.available = False
            self.shutdown()
            return False
        log.info('soft voice ready (%s)', os.path.basename(self.model))
        return True

    def _read(self):
        line = self.proc.stdout.readline()
        try:
            return json.loads(line) if line else None
        except ValueError:
            return None

    def _locked(self, fn, *args):
        with self._lock:
            return fn(*args)

    def warm_up(self):
        """Load the voice in the background so the first sentence is quick."""
        threading.Thread(target=self._locked, args=(self._ensure,), daemon=True).start()

    def synth(self, text, length_scale, out_path):
        return self._locked(self._synth, text, length_scale, out_path)

    def _synth(self, text, length_scale, out_path):
        if not self.available or not self._ensure():
            return False
        req_id = next(self._ids)
        try:
            self.proc.stdin.write(json.dumps({'id': req_id, 'text': text, 'out': out_path,
                                              'length_scale': length_scale}) + '\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            self.proc = None
            return False
        while True:
            msg = self._read()
            if msg is None:
                self.proc = None
                return False
            if msg.get('id') == req_id:
                if msg.get('event') != 'done':
                    log.warning('soft voice: %s', msg.get('text'))
                return msg.get('event') == 'done'

    def shutdown(self):
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                proc.stdin.close()
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()


# ---------------------------------------------------------------- playback
def spawn(argv, on_exit):
    """Start a process owned by GLib (so only GLib reaps it). Returns its pid."""
    flags = (GLib.SpawnFlags.DO_NOT_REAP_CHILD | GLib.SpawnFlags.STDOUT_TO_DEV_NULL
             | GLib.SpawnFlags.STDERR_TO_DEV_NULL)
    pid, _, _, _ = GLib.spawn_async(argv, flags=flags)

    def exited(pid, _status):
        GLib.spawn_close_pid(pid)
        on_exit()
    GLib.child_watch_add(GLib.PRIORITY_DEFAULT, pid, exited)
    return pid


def kill(pid):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def find_player():
    for cmd, args in (('pw-play', []), ('paplay', []), ('aplay', ['-q'])):
        path = shutil.which(cmd)
        if path:
            return [path, *args]
    return None


class LinuxVoice(SpeechOutput):
    def __init__(self, piper=None):
        self.player = find_player()
        if self.player is None:
            raise OSError('no audio player (pw-play, paplay or aplay) found')
        try:
            self.espeak = Espeak()
        except OSError as e:
            log.info('espeak-ng unavailable: %s', e)
            self.espeak = None
        self.piper = piper if piper is not None else Piper()
        if not self.piper.available and self.espeak is None:
            raise OSError('no speech engine (Piper or espeak-ng) found')
        if self.piper.available:
            self.piper.warm_up()
        self.pitch, self.speed, self.volume, self.robotic = 75, 1.0, 0.8, False
        self.rng = random.Random()
        self._job = itertools.count()
        self._current = None          # (job id, on_done) of what he is saying
        self._playing = None          # (job id, player pid, wav path)
        self._dir = os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()

    def configure(self, settings):
        self.pitch = settings.voice_pitch
        self.speed = settings.voice_speed
        self.volume = settings.voice_volume
        self.robotic = settings.robot_effect

    # ------------------------------------------------------------ rendering
    def _render(self, text, style, params):
        """Background thread: returns (samples, sample_rate)."""
        pitch, speed, volume, robotic = params
        if style == 'evil' and self.espeak:
            raw = self.espeak.synth(text, ESPEAK_EVIL, BASE_WPM * 0.9 * speed, EVIL_PITCH)
            return audio.robotize(raw, self.espeak.rate, volume, True, self.rng,
                                  evil=True), self.espeak.rate
        if robotic and self.espeak:
            raw = self.espeak.synth(text, ESPEAK_NICE, BASE_WPM * speed, pitch)
            return audio.robotize(raw, self.espeak.rate, volume, True, self.rng), self.espeak.rate
        if self.piper.available:
            factor = nice_pitch_factor(pitch)
            fd, tmp = tempfile.mkstemp(prefix='robo-piper-', suffix='.wav', dir=self._dir)
            os.close(fd)
            try:
                if self.piper.synth(text, factor / speed, tmp):
                    raw, rate = audio.read_wav(tmp)
                    return audio.soften(raw, rate, volume, factor), rate
            finally:
                os.unlink(tmp)
        if self.espeak is None:
            raise OSError('no speech engine available')
        raw = self.espeak.synth(text, ESPEAK_NICE, BASE_WPM * speed, pitch)   # gentle fallback
        return audio.soften(raw, self.espeak.rate, volume), self.espeak.rate

    # ------------------------------------------------------------ SpeechOutput
    def say(self, text, on_started, on_done, style='normal'):
        self.stop()
        job = next(self._job)
        self._current = (job, on_done)
        params = (self.pitch, self.speed, self.volume, self.robotic)
        threading.Thread(target=self._prepare, args=(job, text, style, params, on_started),
                         daemon=True).start()

    def _prepare(self, job, text, style, params, on_started):
        try:
            samples, rate = self._render(text, style, params)
            env = audio.envelope(samples, rate, FRAME, PLAYBACK_LATENCY_FRAMES)
            fd, path = tempfile.mkstemp(prefix='robo-voice-', suffix='.wav', dir=self._dir)
            os.close(fd)
            audio.write_wav(path, samples, rate)
        except Exception as e:  # noqa: BLE001 - never crash the robot over a voice problem
            log.warning('speech failed: %s', e)
            GLib.idle_add(self._finish, job)
            return
        utt = Utterance(text, env, FRAME, len(samples) / rate + 0.1)
        GLib.idle_add(self._play, job, path, utt, on_started)

    def _play(self, job, path, utt, on_started):
        if self._current is None or self._current[0] != job:   # stopped meanwhile
            os.unlink(path)
            return False
        try:
            pid = spawn([*self.player, path], lambda: self._finish(job))
        except GLib.Error as e:
            log.warning('could not play audio: %s', e.message)
            os.unlink(path)
            self._finish(job)
            return False
        self._playing = (job, pid, path)
        on_started(utt)
        return False

    def _finish(self, job):
        """Clean up after `job` (only touches state that belongs to it)."""
        if self._playing is not None and self._playing[0] == job:
            _, _pid, path = self._playing
            self._playing = None
            try:
                os.unlink(path)
            except OSError:
                pass
        if self._current is not None and self._current[0] == job:
            on_done = self._current[1]
            self._current = None
            on_done()
        return False

    def stop(self):
        if self._current is None:
            return
        job = self._current[0]
        if self._playing is not None and self._playing[0] == job:
            kill(self._playing[1])
        self._finish(job)

    def shutdown(self):
        self.stop()
        self.piper.shutdown()


class SpdSayVoice(SpeechOutput):
    """Last resort: the system's speech-dispatcher voice (the mouth moves to
    a made-up rhythm)."""

    def __init__(self):
        self.path = shutil.which('spd-say')
        if not self.path:
            raise OSError('spd-say not found')
        self.pitch, self.speed, self.volume = 75, 1.0, 0.8
        self._pid = None
        self._on_done = None

    def configure(self, settings):
        self.pitch, self.speed, self.volume = (settings.voice_pitch, settings.voice_speed,
                                               settings.voice_volume)

    def say(self, text, on_started, on_done, style='normal'):
        self.stop()
        self._on_done = on_done
        pitch = -60 if style == 'evil' else int((self.pitch - 50) * 2)
        args = [self.path, '-w', '-p', str(pitch), '-r', str(int((self.speed - 1) * 100)),
                '-i', str(int(self.volume * 200 - 100)), text]
        self._pid = spawn(args, self._done)
        duration = max(0.8, len(text.split()) / (2.6 * self.speed))
        frames = int(duration / FRAME)
        on_started(Utterance(text, [0.7 if (i // 3) % 2 else 0.2 for i in range(frames)],
                             FRAME, duration))

    def _done(self):
        cb, self._on_done, self._pid = self._on_done, None, None
        if cb:
            cb()

    def stop(self):
        if self._pid is not None:
            spawn([self.path, '-S'], lambda: None)       # tell speech-dispatcher to hush
            kill(self._pid)
        self._done()


def create_voice():
    for cls in (LinuxVoice, SpdSayVoice):
        try:
            voice = cls()
            log.info('voice: %s', cls.__name__)
            return voice
        except OSError as e:
            log.info('%s unavailable: %s', cls.__name__, e)
    return None
