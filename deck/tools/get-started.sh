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
flatpak_apps="$(deck_flatpak_apps)"
flatpak_has() { [[ $'\n'"$flatpak_apps"$'\n' == *$'\n'"$1"$'\n'* ]]; }
emus=0; for row in "${DECK_EMULATORS[@]}"; do IFS='|' read -r _n id _s <<<"$row"; flatpak_has "$id" && emus=$((emus + 1)); done
bios_missing="$(deck_bios_report | awk -F'\t' '$1=="missing"{n++} END{print n+0}')"
remote_ok=0
if command -v rclone >/dev/null 2>&1 && [ -n "$SYNC_REMOTE" ] && rclone listremotes 2>/dev/null | grep -qx "${SYNC_REMOTE%%:*}:"; then remote_ok=1; fi
inbox_n=0; [ -d "$INBOX" ] && inbox_n="$(find "$INBOX" -maxdepth 1 -type f \( -iname '*.nes' -o -iname '*.sfc' -o -iname '*.smc' -o -iname '*.gba' -o -iname '*.gb' -o -iname '*.gbc' -o -iname '*.z64' -o -iname '*.n64' -o -iname '*.md' -o -iname '*.iso' -o -iname '*.chd' -o -iname '*.nds' -o -iname '*.cue' \) 2>/dev/null | wc -l)"
if [ "${1:-}" = "--status" ]; then
  plural() { [ "$1" -eq 1 ] && printf '%s %s' "$1" "$2" || printf '%s %s' "$1" "$3"; }
  # (Each line: key|done|label|detail in English|code;values, which Arcadia turns into words it can translate.)
  if [ "$games" -gt 0 ]; then d="$(plural "$games" game games) found in $(plural "$systems" console consoles)"; c="found;$games;$systems"
  else d="none found in $roms yet"; c="none;$roms"; fi
  [ "$inbox_n" -gt 0 ] && d="$d, $(plural "$inbox_n" "new one" "new ones") in Downloads" && c="$c;$inbox_n"
  printf 'games|%s|Games|%s|%s\n' "$([ "$games" -gt 0 ] && echo 1 || echo 0)" "$d" "$c"
  # What your games need (apps and RetroArch cores), worked out by the emulator installer.
  st="$(ARCADIA_ROMS="$roms" python3 "$(dirname "$(readlink -f "$0")")/../lib/emulators.py" status 2>/dev/null)"
  if [ -z "$st" ]; then st="$([ "$emus" -gt 0 ] && echo 1 || echo 0)|$([ "$emus" -gt 0 ] && echo "$emus installed" || echo "none installed yet")"; fi
  printf 'emulators|%s|Emulators|%s\n' "${st%%|*}" "${st#*|}"
  if deck_is_done controls; then
    set_up=(); for e in org.duckstation.DuckStation:DuckStation net.pcsx2.PCSX2:PCSX2 org.libretro.RetroArch:RetroArch; do
      flatpak_has "${e%%:*}" && set_up+=("${e#*:}"); done
    if [ "${#set_up[@]}" -eq 0 ]; then d="set up"; c="set"; elif [ "${#set_up[@]}" -eq 1 ]; then d="set up for ${set_up[0]}"; c="set;${set_up[0]}"
    else names="$(IFS=,; echo "${set_up[*]:0:${#set_up[@]}-1}" | sed 's/,/, /g') and ${set_up[-1]}"; d="set up for $names"; c="setmany;$(IFS=,; echo "${set_up[*]:0:${#set_up[@]}-1}" | sed 's/,/, /g');${set_up[-1]}"; fi
  else d="not set up yet"; c="todo"; fi
  printf 'controls|%s|Controls|%s|%s\n' "$(deck_is_done controls && echo 1 || echo 0)" "$d" "$c"
  if deck_is_done folder-access; then d="emulators can see your games"; c="yes"; else d="emulators can't see your games yet"; c="no"; fi
  printf 'access|%s|Folder access|%s|%s\n' "$(deck_is_done folder-access && echo 1 || echo 0)" "$d" "$c"
  if [ "$remote_ok" -eq 1 ]; then d="syncing to Google Drive"; c="on"; else d="not connected yet"; c="off"; fi
  printf 'saves|%s|Cloud saves|%s|%s\n' "$remote_ok" "$d" "$c"
  if [ "$bios_missing" -eq 0 ]; then d="all the ones needed are there"; c="ok"; else d="$bios_missing missing"; c="missing;$bios_missing"; fi
  printf 'bios|%s|BIOS files|%s|%s\n' "$([ "$bios_missing" -eq 0 ] && echo 1 || echo 0)" "$d" "$c"
  dh="$(deck_deckhand_ok)"
  if [ "$dh" = 1 ]; then d="Deckhand is installed"; c="yes"; else d="not installed yet: Arcadia's sister app"; c="no"; fi
  printf 'deckhand|%s|Windows games|%s|%s\n' "$dh" "$d" "$c"
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
  mark "$remote_ok" "connected to Google Drive"
  [ "$remote_ok" -eq 0 ] && echo "   → pick Cloud saves → Connect (in Desktop Mode: it signs in with your browser)"
  echo; echo "Windows games, stores and streaming"
  mark "$(deck_deckhand_ok)" "Deckhand, Arcadia's sister app"
  [ "$(deck_deckhand_ok)" = 0 ] && echo "   → pick “Windows games” to install it"
} > "${TMPDIR:-/tmp}/deck-started.$$"
deck_say "Get started" "$(cat "${TMPDIR:-/tmp}/deck-started.$$")"
rm -f "${TMPDIR:-/tmp}/deck-started.$$"
