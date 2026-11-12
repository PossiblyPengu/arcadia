#!/usr/bin/env bash
# Install the emulators ES-DE finds on a Steam Deck (Flatpak), skipping the ones already there. Pass names to pick some.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
command -v flatpak >/dev/null 2>&1 || { deck_say "Emulators" "Flatpak isn't installed, so emulators can't be installed from here."; exit 0; }
want=" $* "; done_list=""; failed=""
for row in "${DECK_EMULATORS[@]}"; do
  IFS='|' read -r name id _systems <<<"$row"
  if [ "$#" -gt 0 ] && [[ "${want,,}" != *" ${name,,} "* ]]; then continue; fi
  if deck_flatpak_installed "$id"; then continue; fi
  deck_log "installing $name ($id)"
  if flatpak install --user -y --noninteractive flathub "$id" >> "$DECK_LOG" 2>&1; then done_list+="  • $name"$'\n'; else failed+="  • $name"$'\n'; fi
done
msg="Installed:"$'\n'"${done_list:-  (nothing new)}"
[ -n "$failed" ] && msg+=$'\n'"Couldn't install:"$'\n'"$failed(see $DECK_LOG)"
deck_say "Emulators" "$msg"
