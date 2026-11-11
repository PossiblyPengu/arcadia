#!/usr/bin/env bash
# Set Arcadia up on this machine (a Steam Deck in Desktop Mode, or any Linux PC):
#   - a private Python environment with what Arcadia needs (it doesn't touch the system's Python)
#   - a menu entry "Arcadia" (a .desktop file), so it appears in the application menu
# Needs python3 with the venv module and an internet connection. Nothing is added to Steam, and nothing outside
# the two places below is changed.
#
#   ./install.sh              set up
#   ./install.sh --uninstall  remove the environment and the menu entry (never your ROMs, saves or library)
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="${ARCADIA_VENV:-$DATA/arcadia-env}"
APPS="${ARCADIA_DESKTOP_DIR:-$DATA/applications}"
ENTRY="$APPS/arcadia.desktop"

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$VENV"
  rm -f "$ENTRY"
  echo "Removed $VENV and $ENTRY. Your Arcadia folder (ROMs, saves, library) was not touched."
  exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 isn't installed." >&2; exit 1; }

echo "Making Arcadia's Python environment in $VENV ..."
python3 -m venv "$VENV"

if [ "${ARCADIA_SKIP_PIP:-}" != 1 ]; then
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  echo "Installing PySide6 (the interface; a large download, so it takes a minute) ..."
  "$VENV/bin/python" -m pip install "PySide6>=6.6"
  echo "Installing evdev (optional: direct controller input) ..."
  "$VENV/bin/python" -m pip install "evdev>=1.6" \
    || echo "evdev couldn't be installed (it needs a compiler); that's fine, Steam Input still maps the controls to the keyboard."
fi

chmod +x "$HERE/arcadia.sh"
mkdir -p "$APPS"
cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Arcadia
Comment=Emulator launcher and ROM library
Exec="$HERE/arcadia.sh"
Path=$HERE
Icon=$HERE/arcadia/assets/icon.png
Terminal=false
Categories=Game;Emulator;
EOF
chmod +x "$ENTRY"

echo
echo "Done. Start Arcadia from the application menu (Games), or run:  $HERE/arcadia.sh"
echo "To use it from Game Mode, add $HERE/arcadia.sh to Steam yourself (Steam > Add a Non-Steam Game); see the README."
