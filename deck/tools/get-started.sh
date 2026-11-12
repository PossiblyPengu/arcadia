#!/usr/bin/env bash
# A checklist of what's ready and what to do next: ROMs, emulators, BIOS files, cloud saves.
# With --status it prints one line per item for Arcadia's Setup screen instead:  key|done|label|detail
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
mark() { if [ "$1" = 1 ]; then printf '✓  %s\n' "$2"; else printf '○  %s\n' "$2"; fi; }
roms="$(deck_rom_root)"
systems=0; games=0
if [ -d "$roms" ]; then
  while IFS= read -r d; do
    n="$(find "$d" -maxdepth 2 -type f ! -name '*.txt' ! -name '*.xml' ! -name '.*' 2>/dev/null | wc -l)"
    [ "$n" -gt 0 ] && { systems=$((systems + 1)); games=$((games + n)); }
  done < <(find "$roms" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
fi
emus=0; if command -v flatpak >/dev/null 2>&1; then for row in "${DECK_EMULATORS[@]}"; do IFS='|' read -r _n id _s <<<"$row"; deck_flatpak_installed "$id" && emus=$((emus + 1)); done; fi
bios_missing="$(deck_bios_report | awk -F'\t' '$1=="missing"{n++} END{print n+0}')"
rclone_ok=0; remote_ok=0
if command -v rclone >/dev/null 2>&1; then rclone_ok=1; [ -n "$SYNC_REMOTE" ] && rclone listremotes 2>/dev/null | grep -qx "${SYNC_REMOTE%%:*}:" && remote_ok=1; fi
inbox_n=0; [ -d "$INBOX" ] && inbox_n="$(find "$INBOX" -maxdepth 1 -type f \( -iname '*.nes' -o -iname '*.sfc' -o -iname '*.smc' -o -iname '*.gba' -o -iname '*.gb' -o -iname '*.gbc' -o -iname '*.z64' -o -iname '*.n64' -o -iname '*.md' -o -iname '*.iso' -o -iname '*.chd' -o -iname '*.nds' -o -iname '*.cue' \) 2>/dev/null | wc -l)"
if [ "${1:-}" = "--status" ]; then
  plural() { [ "$1" -eq 1 ] && printf '%s %s' "$1" "$2" || printf '%s %s' "$1" "$3"; }
  if [ "$games" -gt 0 ]; then d="$(plural "$games" game games) found in $(plural "$systems" console consoles)"; else d="none found in $roms yet"; fi
  [ "$inbox_n" -gt 0 ] && d="$d, $(plural "$inbox_n" "new one" "new ones") in Downloads"
  printf 'games|%s|Games|%s\n' "$([ "$games" -gt 0 ] && echo 1 || echo 0)" "$d"
  if [ "$emus" -gt 0 ]; then d="$emus installed"; else d="none installed yet"; fi
  printf 'emulators|%s|Emulators|%s\n' "$([ "$emus" -gt 0 ] && echo 1 || echo 0)" "$d"
  if deck_is_done controls; then d="set up for DuckStation, PCSX2 and RetroArch"; else d="not set up yet"; fi
  printf 'controls|%s|Controls|%s\n' "$(deck_is_done controls && echo 1 || echo 0)" "$d"
  if deck_is_done folder-access; then d="emulators can see your games"; else d="emulators can't see your games yet"; fi
  printf 'access|%s|Folder access|%s\n' "$(deck_is_done folder-access && echo 1 || echo 0)" "$d"
  if [ "$remote_ok" -eq 1 ]; then d="syncing to ${SYNC_REMOTE%%:*}"; elif [ "$rclone_ok" -eq 1 ]; then d="not connected yet"; else d="needs rclone"; fi
  printf 'saves|%s|Cloud saves|%s\n' "$remote_ok" "$d"
  if [ "$bios_missing" -eq 0 ]; then d="all the ones needed are there"; else d="$bios_missing missing"; fi
  printf 'bios|%s|BIOS files|%s\n' "$([ "$bios_missing" -eq 0 ] && echo 1 || echo 0)" "$d"
  dh="$(deck_deckhand_ok)"
  if [ "$dh" = 1 ]; then d="Deckhand is installed"; else d="not installed yet: Arcadia's sister app"; fi
  printf 'deckhand|%s|Windows games and stores|%s\n' "$dh" "$d"
  printf 'inbox|%s|Downloads|%s\n' "$inbox_n" "$INBOX"
  exit 0
fi
{
  echo "Games"
  mark "$([ "$games" -gt 0 ] && echo 1 || echo 0)" "$games game file(s) in $systems system folder(s) under $roms"
  [ "$inbox_n" -gt 0 ] && echo "   → $inbox_n ROM-like file(s) in $INBOX: pick “Sort downloads into ROM folders”"
  echo; echo "Emulators"
  mark "$([ "$emus" -gt 0 ] && echo 1 || echo 0)" "$emus Flatpak emulator(s) installed"
  [ "$emus" -eq 0 ] && echo "   → pick “Install emulators”"
  mark "$([ "$bios_missing" -eq 0 ] && echo 1 || echo 0)" "BIOS files: $([ "$bios_missing" -eq 0 ] && echo 'all required ones found' || echo "$bios_missing required one(s) missing")"
  [ "$bios_missing" -gt 0 ] && echo "   → pick “Check BIOS files” to see which; bring your own dumps to $BIOS_DIR"
  echo; echo "Cloud saves"
  mark "$rclone_ok" "rclone installed"
  mark "$remote_ok" "remote “${SYNC_REMOTE%%:*}” set up in rclone"
  [ "$remote_ok" -eq 0 ] && echo "   → run  rclone config  once and create a Google Drive remote called gdrive"
  echo; echo "Windows games, stores and streaming"
  mark "$(deck_deckhand_ok)" "Deckhand, Arcadia's sister app"
  [ "$(deck_deckhand_ok)" = 0 ] && echo "   → pick “Windows games and stores” to install it"
} > "${TMPDIR:-/tmp}/deck-started.$$"
deck_say "Get started" "$(cat "${TMPDIR:-/tmp}/deck-started.$$")"
rm -f "${TMPDIR:-/tmp}/deck-started.$$"
