#!/usr/bin/env bash
# Let the Flatpak emulators see your ROM and BIOS folders (Flatpak apps can't read other folders unless told they may).
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
command -v flatpak >/dev/null 2>&1 || { deck_say "Folder access" "Flatpak isn't installed."; exit 0; }
dirs=("$(deck_rom_root)"); [ -d "$BIOS_DIR" ] && dirs+=("$BIOS_DIR"); for d in "${SAVE_DIRS[@]}"; do [ -d "$d" ] && dirs+=("$d"); done
n=0; list=""
for row in "${DECK_EMULATORS[@]}"; do
  IFS='|' read -r name id _s <<<"$row"
  deck_flatpak_installed "$id" || continue
  args=(); for d in "${dirs[@]}"; do [ -d "$d" ] && args+=("--filesystem=$d"); done
  flatpak override --user "${args[@]}" "$id" >> "$DECK_LOG" 2>&1 && { n=$((n + 1)); list+="  • $name"$'\n'; }
done
if [ "$n" -eq 0 ]; then deck_say "Folder access" "No Flatpak emulators are installed yet."; else deck_say "Folder access" "These can now see ${dirs[*]}:"$'\n'"$list"; fi
