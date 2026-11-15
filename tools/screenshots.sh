#!/usr/bin/env bash
# Take the docs screenshots (docs/screenshots) from a running Arcadia, the same way every time.
#
#   tools/screenshots.sh path/to/arcadia [OUT_DIR]      (OUT_DIR defaults to docs/screenshots)
#
# A sample home with made-up games on a few consoles, Arcadia at 1280x800 on a virtual screen (Xvfb, unless DISPLAY is
# set), keys for the D-pad and buttons (Return = A, BackSpace = B, Escape = the menu), and ImageMagick's `import` for
# the pictures. Needs xvfb, xdotool and imagemagick.
set -uo pipefail

BIN="$(readlink -f "${1:?the arcadia binary}")"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$(readlink -f "${2:-$HERE/docs/screenshots}")"
WORK="$(mktemp -d)"
trap 'kill "${XVFB:-}" "${PID:-}" 2>/dev/null; rm -rf "$WORK"' EXIT
export SDL_AUDIODRIVER=dummy
mkdir -p "$OUT"

if [ -z "${DISPLAY:-}" ]; then
  Xvfb :92 -screen 0 1280x800x24 >/dev/null 2>&1 &
  XVFB=$!
  export DISPLAY=:92
  sleep 2
fi

press() {
  local win
  win="$(xdotool search --name '^Arcadia$' 2>/dev/null | tail -1)"
  [ -n "$win" ] && xdotool windowfocus --sync "$win" 2>/dev/null
  for k in "$@"; do
    case "$k" in w:*) sleep "${k#w:}" ;; *) xdotool key "$k"; sleep 0.8 ;; esac
  done
}
shot() { sleep "${WAIT:-2}"; import -window root "$OUT/$1.png" && echo "  $1.png"; }

# A home's settings: no update notice in the pictures.
settings() {
  mkdir -p "$1/Arcadia/settings"
  printf '<?xml version="1.0"?>\n<string name="ApplicationUpdaterFrequency" value="never" />\n' \
    > "$1/Arcadia/settings/es_settings.xml"
}

# start HOME: Arcadia on that home; waits for its window
start() {
  "$BIN" --home "$1" --resolution 1280 800 >/dev/null 2>&1 &
  PID=$!
  for _ in $(seq 1 120); do xdotool search --name '^Arcadia$' >/dev/null 2>&1 && break; sleep 0.5; done
}
stop() { kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; PID=""; }

# The home the pictures are taken in. SHOTS_HOME=/home/deck (in a container) makes the paths on screen look like a
# Deck's; it's emptied first, so never point it at a real home.
home="${SHOTS_HOME:-$WORK/home}"
case "$home" in "$HOME"|"$HOME"/) echo "SHOTS_HOME is your own home: refusing (it would be emptied)"; exit 1 ;; esac
rm -rf "${home:?}/ROMs" "${home:?}/Arcadia"

# 1. The first start, with no games: the welcome screen.
mkdir -p "$home/ROMs"
settings "$home"
start "$home"
sleep 10; shot first-start
stop

# 2. With games: made-up titles on a few consoles (empty files are enough to list them).
declare -A games=(
  [nes]="Star Rally.nes|Castle of Lanterns.nes|Moonbase Kids.nes"
  [snes]="Sky Garden Racer.sfc|The Quiet Forest.sfc|Puzzle Lighthouse.sfc"
  [gb]="Pocket Comet.gb|Tiny Tower Tales.gb"
  [gba]="Coral Quest Advance.gba|Neon Courier.gba"
  [megadrive]="Turbo Hedge Runner.md|Saturn Ring Patrol.md"
  [psx]="Polygon Pilots.cue"
)
for sys in "${!games[@]}"; do
  mkdir -p "$home/ROMs/$sys"
  IFS='|' read -ra names <<<"${games[$sys]}"
  for n in "${names[@]}"; do : > "$home/ROMs/$sys/$n"; done
done
settings "$home"
start "$home"
WAIT=0.3 shot boot                                   # (the splash, while it loads)
sleep 10; shot consoles
press Return w:2; shot games-shelf
press Escape w:2 Return w:5; shot setup              # Settings → Setup (its checklist takes a moment)
press BackSpace Down Return w:2; shot main-menu      # Look and feel
press BackSpace Down Return w:2; shot sound-settings # Sound
press BackSpace Up Up Return w:5 Right Down Down Down Return w:5; shot setup-emulators   # Setup → Tools → Emulators
stop
echo "Screenshots in $OUT"
