#!/usr/bin/env bash
# Back up ES-DE's settings, game lists (favorites, play counts), custom systems, collections and the deck config.
#   backup.sh                 make a backup in ~/ES-DE/backups
#   backup.sh --saves         also include the folders listed as saves (SAVE_DIRS)
#   backup.sh --restore [F]   restore the newest backup (or file F); the current state is backed up first
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
B="$DECK_HOME/backups"; mkdir -p "$B"
items=(settings gamelists custom_systems collections deck.conf)
if [ "${1:-}" = "--restore" ]; then
  file="${2:-$(ls -1t "$B"/es-de-backup-*.tar.gz 2>/dev/null | head -n 1)}"
  [ -f "$file" ] || { deck_say "Restore" "There's no backup to restore in $B."; exit 0; }
  keep="$B/before-restore-$(date +%Y%m%d-%H%M%S).tar.gz"
  cur=(); for i in "${items[@]}"; do [ -e "$DECK_HOME/$i" ] && cur+=("$i"); done
  [ "${#cur[@]}" -gt 0 ] && tar -C "$DECK_HOME" -czf "$keep" "${cur[@]}"
  if tar -C "$DECK_HOME" -xzf "$file"; then deck_say "Restore" "Restored $(basename "$file"). Your previous settings were kept in $(basename "$keep"). Restart ES-DE to use them."
  else deck_say "Restore" "The backup couldn't be read, so nothing was changed."; fi
  exit 0
fi
stamp="$(date +%Y%m%d-%H%M%S)"; out="$B/es-de-backup-$stamp.tar.gz"
have=(); for i in "${items[@]}"; do [ -e "$DECK_HOME/$i" ] && have+=("$i"); done
extra=()
if [ "${1:-}" = "--saves" ]; then for d in "${SAVE_DIRS[@]}"; do [ -d "$d" ] && extra+=("$d"); done; fi
if [ "${#have[@]}" -eq 0 ] && [ "${#extra[@]}" -eq 0 ]; then deck_say "Backup" "There's nothing to back up yet."; exit 0; fi
args=(-C "$DECK_HOME" "${have[@]}"); for d in "${extra[@]}"; do args+=(-C / "${d#/}"); done
if tar -czf "$out" "${args[@]}"; then deck_say "Backup" "Saved $(basename "$out") ($(du -h "$out" | cut -f1)) in $B."; else deck_say "Backup" "The backup couldn't be made."; rm -f "$out"; fi
