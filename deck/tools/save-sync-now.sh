#!/usr/bin/env bash
# Sync saves with the cloud right now: newest wins, nothing is deleted.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
if [ -z "$SYNC_REMOTE" ] || [ "$SYNC_ENABLED" != 1 ]; then deck_say "Save sync" "Save sync is off. Set SYNC_REMOTE in $DECK_CONF (see deck/README.md)."; exit 0; fi
if ! command -v rclone >/dev/null 2>&1; then deck_say "Save sync" "Cloud saves aren't connected yet. Choose Setup → Cloud saves → Connect."; exit 0; fi
deck_sync pull
deck_sync push
deck_say "Save sync" "Done. Saves in ${#SAVE_DIRS[@]} folder(s) were synced with $SYNC_REMOTE. Details: $DECK_LOG"
