#!/usr/bin/env bash
# Update this Arcadia fork and the deck extras from the project's GitHub releases.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
command -v python3 >/dev/null 2>&1 || { deck_say "Update Arcadia" "python3 isn't installed."; exit 0; }
[ -n "$APPIMAGE_PATH" ] && export DECK_APPIMAGE="$APPIMAGE_PATH"
out="$(python3 "$(dirname "$(readlink -f "$0")")/../lib/selfupdate.py" "$@" 2>&1)"
deck_say "Update Arcadia" "$out"
