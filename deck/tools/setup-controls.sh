#!/usr/bin/env bash
# Starter controller settings for the Flatpak emulators (DuckStation, PCSX2, RetroArch hotkeys). Pass --reset to replace them.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
command -v python3 >/dev/null 2>&1 || { deck_say "Controls" "python3 isn't installed, so controls can't be set up from here."; exit 0; }
out="$(python3 "$(dirname "$(readlink -f "$0")")/../lib/controls.py" "$@" 2>&1)" && deck_mark_done controls
deck_say "Emulator controls" "$out"
