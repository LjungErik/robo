"""Robo's ears on Linux: offline speech recognition with Vosk.

Recognition runs in a helper process (stt_worker.py) inside Robo's own
virtualenv, which install.sh sets up:
    ~/.local/share/robo/venv            Python with the `vosk` package
    ~/.local/share/robo/models/vosk-*   the speech model (~70 MB)
The helper only opens the microphone while listening, and is shut down
completely between conversations unless "Hey Robo" listening is on.
"""
import glob
import json
import logging
import os
import shutil
import subprocess

from gi.repository import GLib

from robo.platform.base import SpeechInput

log = logging.getLogger(__name__)

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stt_worker.py')


def data_dir():
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'robo')


def find_model():
    models = sorted(glob.glob(os.path.join(data_dir(), 'models', 'vosk-model*')))
    return next((m for m in models if os.path.isdir(m)), None)


def find_recorder():
    return shutil.which('pw-record') or shutil.which('arecord')


class VoskEars(SpeechInput):
    def __init__(self, python=None, model=None, recorder=None, test_input=None):
        self.python = python or os.path.join(data_dir(), 'venv', 'bin', 'python')
        self.model = model or find_model()
        self.recorder = recorder or find_recorder()
        self.test_input = test_input                  # WAV file instead of the microphone
        if not os.path.exists(self.python):
            self.unavailable_reason = "Robo's speech environment is missing (run install.sh)"
        elif not self.model:
            self.unavailable_reason = 'no speech model found (run install.sh)'
        elif not self.recorder and not test_input:
            self.unavailable_reason = 'no audio recorder (pw-record or arecord) found'
        else:
            self.unavailable_reason = ''
        self.available = not self.unavailable_reason
        self.proc = None
        self._buffer = b''
        self._listening = None        # (on_heard, on_silence, on_partial) while listening
        self._wake = False
        self._on_wake = None

    # ------------------------------------------------------------ worker process
    def _ensure_worker(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        args = [self.python, '-I', WORKER, '--model', self.model]
        args += ['--input', self.test_input] if self.test_input else ['--recorder', self.recorder]
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning('could not start speech recognition: %s', e)
            self.proc = None
            return False
        os.set_blocking(self.proc.stdout.fileno(), False)
        self._buffer = b''
        GLib.io_add_watch(self.proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                          GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
                          self._on_output, self.proc)
        log.info('speech recognition started')
        return True

    def _send(self, command):
        if self.proc is None:
            return
        try:
            self.proc.stdin.write((command + '\n').encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            self.proc = None

    def _stop_worker(self):
        if self.proc is not None:
            self._send('quit')
            proc, self.proc = self.proc, None
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.info('speech recognition stopped (microphone off)')

    def _on_output(self, fd, condition, proc):
        if proc is not self.proc:                     # an old worker
            return False
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return True
        except OSError:
            chunk = b''
        if not chunk:
            log.info('speech recognition exited')
            self.proc = None
            if self._listening:
                _, on_silence, _ = self._listening
                self._listening = None
                on_silence()
            return False
        self._buffer += chunk
        while b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            self._dispatch(msg.get('event'), msg.get('text', ''))
        return True

    def _dispatch(self, event, text):
        if event == 'error':
            log.warning('speech recognition: %s', text)
        elif event == 'partial' and self._listening and self._listening[2]:
            self._listening[2](text)
        elif event in ('heard', 'silence') and self._listening:
            on_heard, on_silence, _ = self._listening
            self._listening = None
            on_heard(text) if event == 'heard' else on_silence()
        elif event == 'wake' and self._wake and self._on_wake and not self._listening:
            self._on_wake()

    # ------------------------------------------------------------ SpeechInput
    def prepare(self):
        """Load the model while Robo says hello (the mic stays closed)."""
        if self.available and self._ensure_worker():
            self._send('idle')

    def listen(self, timeout, on_heard, on_silence, on_partial=None):
        if not self.available or not self._ensure_worker():
            on_silence()
            return
        self._listening = (on_heard, on_silence, on_partial)
        self._send(f'listen {timeout:g}')

    def pause(self):
        self._listening = None
        self._send('idle')

    def set_wake_word(self, enabled, on_wake):
        self._wake, self._on_wake = enabled, on_wake
        if not self.available:
            return
        if enabled:
            if self._ensure_worker():
                self._send('wake')
        elif not self._listening:
            self._stop_worker()       # nothing to listen for: free the mic and memory

    def shutdown(self):
        self._listening = None
        self._stop_worker()
