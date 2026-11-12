#!/usr/bin/env bash
# Update every Flatpak emulator that is installed.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
command -v flatpak >/dev/null 2>&1 || { deck_say "Emulators" "Flatpak isn't installed."; exit 0; }
ids=()
for row in "${DECK_EMULATORS[@]}"; do IFS='|' read -r _n id _s <<<"$row"; deck_flatpak_installed "$id" && ids+=("$id"); done
[ "${#ids[@]}" -gt 0 ] || { deck_say "Emulators" "None of the listed emulators are installed."; exit 0; }
if flatpak update --user -y --noninteractive "${ids[@]}" >> "$DECK_LOG" 2>&1; then deck_say "Emulators" "Checked ${#ids[@]} emulator(s) for updates. Details: $DECK_LOG"; else deck_say "Emulators" "An update didn't finish. Details: $DECK_LOG"; fi
