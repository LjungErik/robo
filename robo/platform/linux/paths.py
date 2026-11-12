"""Where Robo's speech files live (set up by install.sh).

    ~/.local/share/robo/venv          Python with vosk + piper-tts
    ~/.local/share/robo/models/vosk-* speech recognition model
    ~/.local/share/robo/voices/*.onnx Piper voice (the soft voice)
"""
import glob
import os


def data_dir():
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'robo')


def venv_python():
    return os.path.join(data_dir(), 'venv', 'bin', 'python')


def find_model():
    models = sorted(glob.glob(os.path.join(data_dir(), 'models', 'vosk-model*')))
    return next((m for m in models if os.path.isdir(m)), None)


def find_voice():
    voices = sorted(glob.glob(os.path.join(data_dir(), 'voices', '*.onnx')))
    return next((v for v in voices if os.path.exists(v + '.json')), None)
