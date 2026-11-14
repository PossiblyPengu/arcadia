#!/usr/bin/env bash
# Free games: homebrew and freeware Arcadia can download for you (Homebrew Hub and libretro's freeware library).
#   free-games.sh --list         one line per game, for Arcadia's Free games screen
#   free-games.sh --about ID     the game's details
#   free-games.sh --install ID   download it into the right ROM folder
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
ARCADIA_ROMS="$(deck_rom_root)"
export ARCADIA_ROMS ARCADIA_HOME="$DECK_HOME"
FG="$(dirname "$(readlink -f "$0")")/../lib/freegames.py"
case "${1:-}" in
  --list) exec python3 "$FG" list ;;
  --refresh) exec python3 "$FG" list --refresh ;;
  --about) exec python3 "$FG" about "${2:-}" ;;
  --install) set -- install "${2:-}" ;;
  *) deck_say "Free games" "Open Setup in Arcadia and choose Free games to browse them."; exit 0 ;;
esac
if [ "${ARCADIA_OUTPUT:-}" = stdout ]; then python3 "$FG" "$@"; exit $?; fi
out="$(python3 "$FG" "$@" 2>&1)"; rc=$?
deck_say "Free games" "$(grep -v '^@progress ' <<<"$out")"
exit $rc
