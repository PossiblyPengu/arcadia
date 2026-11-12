#!/usr/bin/env bash
# Sort ROMs from your downloads folder into ES-DE's ROM folders. Files are matched by header, extension and disc contents;
# anything uncertain is left where it is. Nothing is overwritten or deleted, and "Undo last ROM sort" puts files back.
#   sort-roms.sh               sort the inbox (Downloads)
#   sort-roms.sh --deep        also look in the folders inside it
#   sort-roms.sh --pick        choose the folder with a dialog (zenity or kdialog)
#   sort-roms.sh --undo        move the last sort's files back
#   sort-roms.sh --quiet ...   no dialog (for the startup hook); the result goes to the log
HERE="$(dirname "$(readlink -f "$0")")"
. "$HERE/../lib/deck-lib.sh"
deck_load_conf
quiet=0; extra=(); folder="$INBOX"; undo=0
for a in "$@"; do
  case "$a" in
    --quiet) quiet=1 ;;
    --deep) extra+=(--deep) ;;
    --undo) undo=1 ;;
    --pick)
      if command -v zenity >/dev/null 2>&1; then folder="$(zenity --file-selection --directory --title "Sort ROMs from which folder?" 2>/dev/null)" || exit 0
      elif command -v kdialog >/dev/null 2>&1; then folder="$(kdialog --getexistingdirectory "$HOME" 2>/dev/null)" || exit 0
      else deck_say "Sort ROMs" "No folder chooser is installed (zenity or kdialog). Set INBOX in $DECK_CONF instead."; exit 0; fi
      extra+=(--deep) ;;
  esac
done
command -v python3 >/dev/null 2>&1 || { deck_say "Sort ROMs" "python3 isn't installed, so ROMs can't be sorted from here."; exit 0; }
mkdir -p "$DECK_HOME/deck-data"
args=(--rom-root "$(deck_rom_root)" --journal "$DECK_HOME/deck-data/sort-journal.json")
if [ "$undo" = 1 ]; then out="$(PYTHONPATH="$HERE/../lib" python3 -m romsort "${args[@]}" --undo 2>&1)"; else
  out="$(PYTHONPATH="$HERE/../lib" python3 -m romsort "${args[@]}" --from "$folder" "${extra[@]}" 2>&1)"; fi
if [ "$quiet" = 1 ]; then deck_log "auto sort: $(printf '%s' "$out" | tail -n 1)"; else deck_say "Sort ROMs" "$out"; fi
