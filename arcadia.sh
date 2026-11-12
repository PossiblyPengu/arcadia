#!/usr/bin/env bash
# Start Arcadia full screen, using its own Python environment (made by ./install.sh).
#
#   ./arcadia.sh                  full screen in Game Mode, an ordinary window on the desktop
#   ./arcadia.sh --fullscreen     full screen, wherever you are
#   ./arcadia.sh --windowed       an ordinary window, even in Game Mode
#   ./arcadia.sh --update         update Arcadia from GitHub and exit (works even if the app won't open)
#   ./arcadia.sh --home DIR       run entirely from this folder (portable mode); other options pass through
#
# Set ARCADIA_DRY_RUN=1 to print what would be run instead of running it.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="${ARCADIA_VENV:-$DATA/arcadia-env}"
LOG="$DATA/arcadia/launch.log"

# Game Mode (a Steam game, or the gamescope session) starts full screen; the desktop starts in a window.
fullscreen=()
if [ -n "${SteamGameId:-}" ] || [ "${XDG_CURRENT_DESKTOP:-}" = "gamescope" ] || [ -n "${GAMESCOPE_WAYLAND_DISPLAY:-}" ] || [ "${ARCADIA_FULLSCREEN:-}" = 1 ]; then
  fullscreen=(--fullscreen)
fi
extra=()
for arg in "$@"; do
  if [ "$arg" = "--windowed" ]; then fullscreen=(); else extra+=("$arg"); fi
done

# Which Python: ours if the installer made one, else one you name, else the system's if it has what we need.
python=""
if [ -x "$VENV/bin/python" ]; then
  python="$VENV/bin/python"
elif [ -n "${ARCADIA_PYTHON:-}" ]; then
  python="$ARCADIA_PYTHON"
elif command -v python3 >/dev/null 2>&1 && python3 -c "import PySide6" >/dev/null 2>&1; then
  python="$(command -v python3)"
fi

if [ -z "$python" ]; then
  mkdir -p "$(dirname "$LOG")"
  msg="Arcadia isn't installed yet. Run  $HERE/install.sh  once (in Desktop Mode, with an internet connection)."
  echo "$msg" | tee "$LOG" >&2
  command -v notify-send >/dev/null 2>&1 && notify-send "Arcadia" "$msg" || true
  exit 1
fi

# In Game Mode (a Steam game's environment) the window system is gamescope's X11; ask Qt for that explicitly.
if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -n "${SteamGameId:-}" ] && [ -n "${DISPLAY:-}" ]; then
  export QT_QPA_PLATFORM=xcb
fi

export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
cd "$HERE"
command=("$python" -m arcadia "${fullscreen[@]}" "${extra[@]}")

if [ "${ARCADIA_DRY_RUN:-}" = 1 ]; then
  printf '%q ' "${command[@]}"; echo
  exit 0
fi
mkdir -p "$(dirname "$LOG")"
# keep the log from growing forever: start over once it passes 1 MB
[ -f "$LOG" ] && [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ] && mv -f "$LOG" "$LOG.old"
exec "${command[@]}" 2>>"$LOG"
