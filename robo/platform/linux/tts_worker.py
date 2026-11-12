#!/usr/bin/env python3
"""Robo's soft voice: a helper process that turns text into speech with Piper.

Runs inside Robo's own virtualenv (it needs the `piper-tts` package), so it
must not import anything from robo. The voice model is loaded once.

Requests (JSON lines on stdin):
    {"id": 1, "text": "Hello!", "out": "/path/file.wav", "length_scale": 1.0}
Answers (JSON lines on stdout):
    {"event": "ready"}
    {"event": "done", "id": 1, "out": "/path/file.wav"}
    {"event": "error", "id": 1, "text": "what went wrong"}
"""
import argparse
import json
import sys
import wave


def emit(**msg):
    sys.stdout.write(json.dumps(msg) + '\n')
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True, help='Piper .onnx voice')
    args = ap.parse_args()
    try:
        from piper import PiperVoice, SynthesisConfig
        voice = PiperVoice.load(args.model)
    except Exception as e:  # noqa: BLE001 - report any setup problem to Robo
        emit(event='error', id=None, text=f'could not load the voice: {e}')
        return 1
    emit(event='ready')
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        try:
            config = SynthesisConfig(length_scale=float(req.get('length_scale', 1.0)),
                                     noise_scale=0.6, noise_w_scale=0.7)
            with wave.open(req['out'], 'wb') as w:
                voice.synthesize_wav(req['text'], w, syn_config=config)
            emit(event='done', id=req.get('id'), out=req['out'])
        except Exception as e:  # noqa: BLE001
            emit(event='error', id=req.get('id'), text=str(e))
    return 0


if __name__ == '__main__':
    sys.exit(main())
