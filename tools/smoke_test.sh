#!/usr/bin/env bash
# Smoke test with no games: start Arcadia with an empty home, do what has crashed it before, quit, and fail on any
# AddressSanitizer report, crash or exit code other than 0.
#
#   tools/smoke_test.sh path/to/arcadia      (best with an ASan build: cmake -DASAN=on)
#
# Runs on a virtual screen (Xvfb) unless DISPLAY is already set; needs xdotool. Keys are Arcadia's keyboard mapping:
# Return = A, BackSpace = B, Left/Right/Up/Down = the D-pad. What it does, each in a fresh run:
#   1. the welcome screen (no games) → Settings → Look and feel: change the colours (back to the welcome screen),
#      then Collections → Group custom collections, and the theme; then quit.
#   2. Setup → Tools → Sort downloads, and quit while that tool is still running (a crash in 0.1.4).
#   3. start in Kid mode with no games, and quit.
set -uo pipefail

BIN="$(readlink -f "${1:?the arcadia binary}")"
WORK="$(mktemp -d)"
trap 'kill "${XVFB:-}" 2>/dev/null; rm -rf "$WORK"' EXIT
export ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:log_path=$WORK/asan"
export UBSAN_OPTIONS="print_stacktrace=1:log_path=$WORK/ubsan"
export SDL_AUDIODRIVER=dummy

if [ -z "${DISPLAY:-}" ]; then
  Xvfb :91 -screen 0 1280x800x24 >/dev/null 2>&1 &
  XVFB=$!
  export DISPLAY=:91
  sleep 2
fi

failed=0
say() { printf '%s\n' "$*"; }

# press KEY... (a pause after each; "w:N" waits N seconds)
press() {
  local win
  win="$(xdotool search --name '^Arcadia$' 2>/dev/null | tail -1)"
  [ -n "$win" ] && xdotool windowfocus --sync "$win" 2>/dev/null
  for k in "$@"; do
    case "$k" in w:*) sleep "${k#w:}" ;; *) xdotool key "$k"; sleep "${STEP:-0.8}" ;; esac
  done
}

# run NAME SETUP-FUNCTION STEPS-FUNCTION [CHECK-FUNCTION]: a fresh empty home, start, wait for the window, do the
# steps, quit; then CHECK (given the home) must say the steps really happened (keys that missed would pass silently).
run() {
  local name="$1" setup="$2" steps="$3" check="${4:-}" home="$WORK/$1" pid rc
  mkdir -p "$home/ROMs"
  "$setup" "$home"
  "$BIN" --home "$home" --resolution 1280 800 > "$WORK/$name.out" 2>&1 &
  pid=$!
  for _ in $(seq 1 120); do
    xdotool search --name '^Arcadia$' >/dev/null 2>&1 && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  sleep "${SETTLE:-8}"
  "$steps" "$pid"
  kill -TERM "$pid" 2>/dev/null  # (what Steam does to close it: SDL turns it into a normal quit)
  for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then
    say "✗ $name: still running a minute after being asked to quit"
    kill -KILL "$pid" 2>/dev/null
    failed=1
    return
  fi
  wait "$pid"; rc=$?
  if ls "$WORK"/asan.* "$WORK"/ubsan.* >/dev/null 2>&1; then
    say "✗ $name: the sanitizer reported a problem:"
    cat "$WORK"/asan.* "$WORK"/ubsan.* 2>/dev/null | head -80
    rm -f "$WORK"/asan.* "$WORK"/ubsan.*
    failed=1
  elif [ "$rc" -ne 0 ]; then
    say "✗ $name: exited with $rc"
    tail -n 40 "$WORK/$name.out"
    tail -n 40 "$home/Arcadia/logs/es_log.txt" 2>/dev/null
    failed=1
  elif [ -n "$check" ] && ! "$check" "$home"; then
    say "✗ $name: the steps didn't do what they should (the keys may not have reached Arcadia)"
    tail -n 30 "$home/Arcadia/logs/es_log.txt" 2>/dev/null
    failed=1
  else
    say "✓ $name"
  fi
}

no_setup() { :; }

look_and_feel() {
  press Return w:2 Down Return w:2          # welcome → Setup (opens Settings) → Look and feel
  press Right BackSpace w:3                 # Colours: the next scheme; saving closes the menu (back to the welcome)
  press Return w:2 Down Return w:2          # Settings → Look and feel again
  press Down Down Return w:2                # Collections
  press Down Down Down Down Right BackSpace w:3   # Group custom collections (the greyed-out row is skipped)
  press Up Right BackSpace w:5              # Theme: the next one; saving reloads
  press BackSpace w:2                       # close Settings
}

setting() { grep -o "name=\"$2\" value=\"[^\"]*\"" "$1/Arcadia/settings/es_settings.xml" 2>/dev/null; }
look_and_feel_done() {  # the colours and the theme were changed and saved
  setting "$1" MenuColorScheme | grep -q 'value="dusk"' && setting "$1" Theme | grep -qv 'value="arcadia"'
}

quit_during_a_tool() {
  press Return w:2 Return w:3               # welcome → Settings → Setup
  STEP=0.5 press Right Return               # Tools → Sort downloads: it starts
  sleep 1                                   # (quit while it runs)
}

tool_started() {  # Sort downloads was started (Arcadia logs each tool it runs)
  grep -q 'GuiToolRunner: running .*sort-roms' "$1/Arcadia/logs/es_log.txt" 2>/dev/null
}

kid_mode() {
  mkdir -p "$1/Arcadia/settings"
  cat > "$1/Arcadia/settings/es_settings.xml" <<'XML'
<?xml version="1.0"?>
<string name="UIMode" value="kid" />
XML
}
just_quit() { :; }

run look-and-feel no_setup look_and_feel look_and_feel_done
run quit-during-a-tool no_setup quit_during_a_tool tool_started
run kid-mode kid_mode just_quit

if [ "$failed" -ne 0 ]; then
  say "Smoke test failed."
  exit 1
fi
say "Smoke test passed."
