#!/usr/bin/env bash
# Installs Robo the desktop companion: dependencies, voice, app launcher, autostart.
#   ./install.sh             everything
#   ./install.sh --no-voice  skip talking (speech recognition + soft voice, ~250 MB)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/robot_companion.py"
NAME="robot-companion"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/robo"
MODEL_NAME="vosk-model-small-en-us-0.15"
MODEL_URL="https://alphacephei.com/vosk/models/$MODEL_NAME.zip"
VOICE_NAME="en_US-hfc_female-medium"
VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/$VOICE_NAME"
WITH_VOICE=1
[ "${1:-}" = "--no-voice" ] && WITH_VOICE=0

missing=()
python3 -c 'import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null \
  || missing+=(python3-gi gir1.2-gtk-3.0)
python3 -c 'import gi; gi.require_foreign("cairo")' 2>/dev/null || missing+=(python3-gi-cairo)
if [ $WITH_VOICE = 1 ]; then
  python3 -c 'import ctypes.util, sys; sys.exit(not ctypes.util.find_library("espeak-ng"))' \
    || missing+=(libespeak-ng1)
  python3 -m venv --help >/dev/null 2>&1 || missing+=(python3-venv)
fi
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing missing packages: ${missing[*]}"
  sudo apt-get install -y "${missing[@]}"
fi

# ---- Robo's ears and soft voice: Vosk + Piper, offline, in their own environment
if [ $WITH_VOICE = 1 ]; then
  if ! "$DATA/venv/bin/python" -c 'import vosk, piper' 2>/dev/null; then
    echo "Setting up speech recognition (Vosk) and Robo's soft voice (Piper)…"
    python3 -m venv "$DATA/venv"
    "$DATA/venv/bin/python" -m pip install -q --disable-pip-version-check vosk piper-tts
  fi
  if [ ! -f "$DATA/voices/$VOICE_NAME.onnx.json" ]; then
    echo "Downloading Robo's voice (~60 MB)…"
    mkdir -p "$DATA/voices"
    curl -fL --progress-bar -o "$DATA/voices/$VOICE_NAME.onnx.part" "$VOICE_URL.onnx"
    curl -fsSL -o "$DATA/voices/$VOICE_NAME.onnx.json.part" "$VOICE_URL.onnx.json"
    mv "$DATA/voices/$VOICE_NAME.onnx.part" "$DATA/voices/$VOICE_NAME.onnx"
    mv "$DATA/voices/$VOICE_NAME.onnx.json.part" "$DATA/voices/$VOICE_NAME.onnx.json"
  fi
  if [ ! -d "$DATA/models/$MODEL_NAME" ]; then
    echo "Downloading the English speech model (~40 MB)…"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    curl -fL --progress-bar -o "$tmp/model.zip" "$MODEL_URL"
    mkdir -p "$DATA/models"
    python3 -I -c 'import zipfile, sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' \
      "$tmp/model.zip" "$DATA/models"
  fi
  echo "Robo can talk! Double-click him to chat. (Check your microphone isn't muted.)"
fi

chmod +x "$APP"

desktop_entry() {
  cat <<EOF
[Desktop Entry]
Type=Application
Name=Robot Companion
Comment=A cute little robot that lives on your desktop
Exec=/usr/bin/python3 "$APP"
Icon=face-smile
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF
}

mkdir -p "$HOME/.config/autostart" "$HOME/.local/share/applications"
desktop_entry > "$HOME/.config/autostart/$NAME.desktop"
desktop_entry > "$HOME/.local/share/applications/$NAME.desktop"
echo "Added to autostart and the app menu."

pkill -f "$APP" 2>/dev/null || true
sleep 0.3
setsid /usr/bin/python3 "$APP" >/dev/null 2>&1 < /dev/null &
echo "Robo is running! Right-click him for options."
