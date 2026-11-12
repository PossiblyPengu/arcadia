#!/usr/bin/env bash
# Install the emulators your games need: the apps from Flathub and, for consoles Arcadia plays through RetroArch, the
# RetroArch cores. With no arguments it installs what your games need; pass names (or Flatpak ids) to pick.
#   install-emulators.sh                 what your games need
#   install-emulators.sh duckstation …   those (and the cores your games need from them)
#   install-emulators.sh --plan          what Arcadia's Emulators screen shows (one line per emulator)
#   install-emulators.sh --remove ID     uninstall one
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
grant=("$(deck_rom_root)"); [ -d "$BIOS_DIR" ] && grant+=("$BIOS_DIR"); for d in "${SAVE_DIRS[@]}"; do [ -d "$d" ] && grant+=("$d"); done
export ARCADIA_GRANT_DIRS="$(IFS=:; echo "${grant[*]}")" ARCADIA_ROMS="$(deck_rom_root)" ARCADIA_HOME="$DECK_HOME"
EMU="$(dirname "$(readlink -f "$0")")/../lib/emulators.py"
case "${1:-}" in
  --plan) exec python3 "$EMU" plan ;;
  --status) exec python3 "$EMU" status ;;
  --remove) set -- remove "${2:-}" ;;
  "") set -- install --needed ;;
  *) set -- install "$@" ;;
esac
if [ "${ARCADIA_OUTPUT:-}" = stdout ]; then python3 "$EMU" "$@"; exit $?; fi
out="$(python3 "$EMU" "$@" 2>&1)"; rc=$?
deck_say "Emulators" "$out"
exit $rc
