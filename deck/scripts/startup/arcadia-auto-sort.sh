#!/usr/bin/env bash
# Runs when ES-DE starts: if AUTO_SORT=1 in ~/ES-DE/deck.conf, sort new ROMs from the inbox into the ROM folders.
. "$(dirname "$(readlink -f "$0")")/../../lib/deck-lib.sh" 2>/dev/null || . "$HOME/ES-DE/deck/lib/deck-lib.sh"
deck_load_conf
[ "$AUTO_SORT" = 1 ] || exit 0
"$(dirname "$(readlink -f "$0")")/../../tools/sort-roms.sh" --quiet 2>/dev/null || "$HOME/ES-DE/deck/tools/sort-roms.sh" --quiet
