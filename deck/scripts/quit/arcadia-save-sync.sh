#!/usr/bin/env bash
# Runs on this ES-DE event: send your saves to the cloud (never deletes anything).
. "$(dirname "$(readlink -f "$0")")/../../lib/deck-lib.sh" 2>/dev/null || . "$HOME/ES-DE/deck/lib/deck-lib.sh"
deck_sync push
