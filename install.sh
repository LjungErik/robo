#!/usr/bin/env bash
# Installs Robo the desktop companion: dependencies, app launcher, autostart.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/robot_companion.py"
NAME="robot-companion"

missing=()
python3 -c 'import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null \
  || missing+=(python3-gi gir1.2-gtk-3.0)
python3 -c 'import gi; gi.require_foreign("cairo")' 2>/dev/null || missing+=(python3-gi-cairo)
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing missing packages: ${missing[*]}"
  sudo apt-get install -y "${missing[@]}"
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
