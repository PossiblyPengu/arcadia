#!/usr/bin/env bash
# Connect cloud saves to Google Drive, without a terminal: get rclone if it isn't here (from rclone.org, checked), then
# sign in to Google in the browser (rclone opens it and finishes by itself). Saves then sync when a game ends.
# Only files Arcadia creates are reachable (Google's "drive.file" access), in the folder named in SYNC_REMOTE.
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
title="Cloud saves"
if [ -z "$SYNC_REMOTE" ] || [ "$SYNC_ENABLED" != 1 ]; then
  deck_say "$title" "Save sync is off. Set SYNC_REMOTE and SYNC_ENABLED=1 in $DECK_CONF to turn it on."; exit 0
fi
remote="${SYNC_REMOTE%%:*}"
if ! command -v rclone >/dev/null 2>&1; then
  echo "Getting rclone, which syncs the saves (from rclone.org, checked against its checksum)…"
  out="$(python3 "$(dirname "$(readlink -f "$0")")/../lib/get_rclone.py" "$DECK_BIN" 2>&1)"; rc=$?
  echo "$out"
  [ "$rc" -eq 0 ] || { deck_say "$title" "Couldn't get rclone. Check that the Deck is online and try again."; exit 1; }
fi
if rclone listremotes 2>/dev/null | grep -qx "$remote:"; then
  deck_mark_done saves
  deck_say "$title" "Connected: saves sync with Google Drive (folder ${SYNC_REMOTE#*:}) when a game ends. \"Sync saves now\" does it right away."
  exit 0
fi
if deck_game_mode; then
  deck_say "$title" "Signing in to Google needs a browser, which Game Mode doesn't have. Do it once in Desktop Mode (STEAM → Power → Switch to Desktop): open Arcadia, then Setup → Cloud saves → Connect."
  exit 0
fi
echo "Opening Google's sign-in in your browser. Choose your account and allow access; this finishes by itself."
echo "(Arcadia can only see the files it makes itself, in a folder called ${SYNC_REMOTE#*:}.)"
if timeout 600 rclone config create "$remote" drive scope=drive.file >> "$DECK_LOG" 2>&1 \
    && rclone listremotes 2>/dev/null | grep -qx "$remote:"; then
  deck_mark_done saves
  deck_say "$title" "Connected to Google Drive. Your saves sync when a game ends; \"Sync saves now\" does it right away."
else
  rclone config delete "$remote" >/dev/null 2>&1
  deck_say "$title" "The sign-in didn't finish (closed, or it took over 10 minutes). Choose Connect to try again."
  exit 1
fi
