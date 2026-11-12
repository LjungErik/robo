"""Robo's voice on Linux.

EspeakVoice talks to the espeak-ng C library directly (ctypes), so it
only needs libespeak-ng (installed with Ubuntu's speech-dispatcher), runs
the robot filter from robo.audio, and plays the result with pw-play/aplay.
SpdSayVoice is a fallback that uses the plain system voice.
"""
import ctypes
import ctypes.util
import itertools
import logging
import os
import random
import shutil
import signal
import tempfile
import threading

from gi.repository import GLib

from robo import audio
from robo.platform.base import SpeechOutput, Utterance

log = logging.getLogger(__name__)

VOICE = 'en-us+f4'            # higher-pitched variant: cute
BASE_WPM = 165
FRAME = 1 / 30
PLAYBACK_LATENCY_FRAMES = 3   # the player needs a moment to start

# espeak-ng constants
AUDIO_OUTPUT_SYNCHRONOUS = 2
POS_CHARACTER = 1
CHARS_UTF8, END_PAUSE = 0x1, 0x1000
P_RATE, P_VOLUME, P_PITCH, P_RANGE = 1, 2, 3, 4
SYNTH_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int,
                                  ctypes.c_void_p)


class Espeak:
    """Minimal binding: synthesise text into a list of samples."""

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

    def synth(self, text, voice=VOICE, wpm=BASE_WPM, pitch=75):
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


class EspeakVoice(SpeechOutput):
    def __init__(self):
        self.engine = Espeak()
        self.player = find_player()
        if self.player is None:
            raise OSError('no audio player (pw-play, paplay or aplay) found')
        self.pitch, self.speed, self.volume, self.effect = 75, 1.0, 0.8, True
        self.rng = random.Random()
        self._job = itertools.count()
        self._current = None          # (job id, on_done) of what he is saying
        self._playing = None          # (job id, player pid, wav path)
        self._dir = os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()

    def configure(self, settings):
        self.pitch = settings.voice_pitch
        self.speed = settings.voice_speed
        self.volume = settings.voice_volume
        self.effect = settings.robot_effect

    def say(self, text, on_started, on_done):
        self.stop()
        job = next(self._job)
        self._current = (job, on_done)
        params = (self.pitch, self.speed, self.volume, self.effect)
        threading.Thread(target=self._prepare, args=(job, text, params, on_started),
                         daemon=True).start()

    def _prepare(self, job, text, params, on_started):
        """Background thread: synthesise + filter + write the WAV."""
        pitch, speed, volume, effect = params
        try:
            raw = self.engine.synth(text, wpm=BASE_WPM * speed, pitch=pitch)
            samples = audio.robotize(raw, self.engine.rate, volume, effect, self.rng)
            env = audio.envelope(samples, self.engine.rate, FRAME, PLAYBACK_LATENCY_FRAMES)
            fd, path = tempfile.mkstemp(prefix='robo-voice-', suffix='.wav', dir=self._dir)
            os.close(fd)
            audio.write_wav(path, samples, self.engine.rate)
        except Exception as e:  # noqa: BLE001 - never crash the robot over a voice problem
            log.warning('speech failed: %s', e)
            GLib.idle_add(self._finish, job)
            return
        utt = Utterance(text, env, FRAME, len(samples) / self.engine.rate + 0.1)
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


class SpdSayVoice(SpeechOutput):
    """Fallback: the system's speech-dispatcher voice (no robot filter, and
    the mouth moves to a made-up rhythm)."""

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

    def say(self, text, on_started, on_done):
        self.stop()
        self._on_done = on_done
        args = [self.path, '-w', '-p', str(int((self.pitch - 50) * 2)),
                '-r', str(int((self.speed - 1) * 100)), '-i', str(int(self.volume * 200 - 100)),
                text]
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
    for cls in (EspeakVoice, SpdSayVoice):
        try:
            voice = cls()
            log.info('voice: %s', cls.__name__)
            return voice
        except OSError as e:
            log.info('%s unavailable: %s', cls.__name__, e)
    return None
