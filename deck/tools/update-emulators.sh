#!/usr/bin/env bash
# Update the installed emulators, and the RetroArch cores that have a newer build.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
export ARCADIA_ROMS="$(deck_rom_root)" ARCADIA_HOME="$DECK_HOME"
EMU="$(dirname "$(readlink -f "$0")")/../lib/emulators.py"
if [ "${ARCADIA_OUTPUT:-}" = stdout ]; then python3 "$EMU" update; exit $?; fi
out="$(python3 "$EMU" update 2>&1)"; rc=$?
out="$(grep -v '^@progress ' <<<"$out")"  # (progress is for Arcadia's own screen)
deck_say "Emulators" "$out"
exit $rc
