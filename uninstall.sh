#!/usr/bin/env bash
# Stops Robo and removes the autostart entry and app launcher.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pkill -f "$DIR/robot_companion.py" 2>/dev/null || true
rm -f "$HOME/.config/autostart/robot-companion.desktop" \
      "$HOME/.local/share/applications/robot-companion.desktop"
echo "Robo has been removed from autostart. (Files in $DIR are untouched.)"
