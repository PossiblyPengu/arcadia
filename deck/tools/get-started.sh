#!/usr/bin/env bash
# A checklist of what's ready and what to do next: ROMs, emulators, BIOS files, cloud saves.
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
} > "${TMPDIR:-/tmp}/deck-started.$$"
deck_say "Get started" "$(cat "${TMPDIR:-/tmp}/deck-started.$$")"
rm -f "${TMPDIR:-/tmp}/deck-started.$$"
