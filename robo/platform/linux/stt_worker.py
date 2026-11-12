#!/usr/bin/env python3
"""Robo's ears: a helper process that turns microphone audio into text.

It runs inside Robo's own virtualenv (it needs the `vosk` package), so it
must not import anything from robo. Everything stays on this computer.

Commands (one per line on stdin):
    listen SECONDS   recognise one sentence; give up after SECONDS of silence
    wake             wait for "hey robo"
    idle             stop listening (the microphone is closed)
    quit
Events (JSON lines on stdout):
    {"event": "ready" | "partial" | "heard" | "silence" | "wake" | "error", "text": "..."}
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import wave

SAMPLE_RATE = 16000
CHUNK_SECONDS = 0.1
WAKE_WORDS = ('robo', 'robot')
WAKE_GRAMMAR = ['hey robo', 'hi robo', 'hello robo', 'okay robo', 'robo',
                'hey robot', 'hi robot', 'robot', '[unk]']
KEEP_LISTENING_WHILE_TALKING = 4.0   # extend the timeout while words keep coming


def emit(event, text=''):
    sys.stdout.write(json.dumps({'event': event, 'text': text}) + '\n')
    sys.stdout.flush()


class Microphone:
    """Raw 16 kHz mono 16-bit audio from pw-record or arecord. The recorder
    only runs while we are listening, so the microphone is otherwise off."""

    def __init__(self, recorder):
        self.recorder = recorder
        self.rate = SAMPLE_RATE
        self.proc = None

    def _command(self):
        if self.recorder.endswith('arecord'):
            return [self.recorder, '-q', '-f', 'S16_LE', '-r', str(self.rate), '-c', '1',
                    '-t', 'raw']
        return [self.recorder, '--rate', str(self.rate), '--channels', '1', '--format', 's16',
                '-']

    def read(self):
        if self.proc is None:
            self.proc = subprocess.Popen(self._command(), stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
        return self.proc.stdout.read(int(self.rate * CHUNK_SECONDS) * 2)

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


class WavFile:
    """For tests: plays a WAV file into the recogniser, then silence."""

    def __init__(self, path):
        with wave.open(path) as w:
            self.rate = w.getframerate()
            self.data = w.readframes(w.getnframes())
        self.pos = None

    def read(self):
        n = int(self.rate * CHUNK_SECONDS) * 2
        if self.pos is None:
            self.pos = 0
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        time.sleep(CHUNK_SECONDS / 4)              # a bit faster than real time
        return chunk if chunk else b'\0' * n

    def stop(self):
        self.pos = None                            # next listen replays the file


def read_commands(q):
    for line in sys.stdin:
        q.put(line.strip())
    q.put('quit')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--recorder', default='pw-record')
    ap.add_argument('--input', help='WAV file instead of the microphone (testing)')
    args = ap.parse_args()

    try:
        import vosk
    except ImportError:
        emit('error', 'the vosk package is not installed')
        return 1
    vosk.SetLogLevel(-1)
    try:
        model = vosk.Model(args.model)
    except Exception as e:  # noqa: BLE001 - report any model problem to Robo
        emit('error', f'could not load the speech model: {e}')
        return 1

    source = WavFile(args.input) if args.input else Microphone(args.recorder)
    commands = queue.Queue()
    threading.Thread(target=read_commands, args=(commands,), daemon=True).start()
    emit('ready')

    mode, rec, deadline, last_partial = 'idle', None, 0.0, ''
    while True:
        try:
            while True:
                cmd, *rest = (commands.get_nowait().split() or [''])
                if cmd == 'listen':
                    mode, last_partial = 'listen', ''
                    rec = vosk.KaldiRecognizer(model, source.rate)
                    deadline = time.monotonic() + (float(rest[0]) if rest else 7.0)
                elif cmd == 'wake':
                    mode = 'wake'
                    rec = vosk.KaldiRecognizer(model, source.rate, json.dumps(WAKE_GRAMMAR))
                elif cmd == 'idle':
                    mode, rec = 'idle', None
                elif cmd == 'quit':
                    source.stop()
                    return 0
        except queue.Empty:
            pass

        if mode == 'idle':
            source.stop()
            time.sleep(0.05)
            continue
        data = source.read()
        if not data:                               # recorder died; try again shortly
            source.stop()
            time.sleep(0.2)
            continue
        now = time.monotonic()

        if mode == 'listen':
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get('text', '').strip()
                if text:
                    emit('heard', text)
                    mode, rec = 'idle', None
                    continue
            else:
                partial = json.loads(rec.PartialResult()).get('partial', '').strip()
                if partial and partial != last_partial:
                    last_partial = partial
                    emit('partial', partial)
                    deadline = max(deadline, now + KEEP_LISTENING_WHILE_TALKING)
            if now > deadline:
                text = json.loads(rec.FinalResult()).get('text', '').strip()
                emit('heard', text) if text else emit('silence')
                mode, rec = 'idle', None
        elif mode == 'wake':
            done = rec.AcceptWaveform(data)
            result = json.loads(rec.Result() if done else rec.PartialResult())
            words = result.get('text' if done else 'partial', '').split()
            if any(w in WAKE_WORDS for w in words):
                emit('wake')
                mode, rec = 'idle', None


if __name__ == '__main__':
    sys.exit(main())
