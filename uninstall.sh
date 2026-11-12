#!/usr/bin/env bash
# Stops Robo and removes the autostart entry and app launcher.
#   ./uninstall.sh          keep settings and the speech model
#   ./uninstall.sh --purge  also delete settings and the speech environment/model
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pkill -f "$DIR/robot_companion.py" 2>/dev/null || true
rm -f "$HOME/.config/autostart/robot-companion.desktop" \
      "$HOME/.local/share/applications/robot-companion.desktop"
echo "Robo has been removed from autostart. (Files in $DIR are untouched.)"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/robo" "${XDG_CONFIG_HOME:-$HOME/.config}/robo"
  echo "Settings, speech environment and speech model deleted."
fi
