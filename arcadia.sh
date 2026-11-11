#!/usr/bin/env bash
# Start Arcadia full screen, using its own Python environment (made by ./install.sh).
#
#   ./arcadia.sh                  full screen (what you want in Game Mode)
#   ./arcadia.sh --windowed       an ordinary window
#   ./arcadia.sh --home DIR       run entirely from this folder (portable mode); other options pass through
#
# Set ARCADIA_DRY_RUN=1 to print what would be run instead of running it.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="${ARCADIA_VENV:-$DATA/arcadia-env}"
LOG="$DATA/arcadia/launch.log"

fullscreen=(--fullscreen)
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
exec "${command[@]}" 2>>"$LOG"
