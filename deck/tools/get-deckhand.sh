#!/usr/bin/env bash
# Deckhand, Arcadia's sister app: Windows programs and games, game stores, streaming and Deck add-ons, straight into
# Steam. Opens it; installs it first with its own installer (which checks the download's checksum) if it isn't there.
# --status prints "1" if Deckhand is installed, else "0".
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
deck_load_conf
bin="$(deck_deckhand_bin)"
if [ "${1:-}" = "--status" ]; then deck_deckhand_ok; exit 0; fi
if [ -z "$bin" ] || [ -e "$DECKHAND_BROKEN" ]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  deck_log "Deckhand: installing from $DECKHAND_GET_URL"
  if ! curl -fsSL --max-time 60 -o "$tmp/get.sh" "$DECKHAND_GET_URL" || ! bash "$tmp/get.sh" >> "$DECK_LOG" 2>&1; then
    deck_say "Deckhand" "Deckhand couldn't be installed. Check that the Deck is online and try again (details are in $DECK_LOG)."
    exit 1
  fi
  bin="$(deck_deckhand_bin)"
  [ -n "$bin" ] || { deck_say "Deckhand" "Deckhand's installer finished, but Deckhand wasn't found afterwards (see $DECK_LOG)."; exit 1; }
  rm -f "$DECKHAND_BROKEN"
  installed="Deckhand is installed. "
fi
# Arcadia waits here while Deckhand is open, the way it waits for a game.
rc=0; "$bin" >> "$DECK_LOG" 2>&1 < /dev/null || rc=$?
if [ "$rc" -ne 0 ]; then
  deck_log "Deckhand: $bin stopped with code $rc"
  : > "$DECKHAND_BROKEN"
  deck_say "Deckhand" "Deckhand didn't start properly (it stopped with code $rc; details are in $DECK_LOG). Pick “Windows games and stores” again to reinstall it."
  exit 1
fi
deck_say "Deckhand" "${installed:-}Deckhand is closed. Open it again from here, or from your Steam library once you've used its ☰ Menu → Add Deckhand to Steam. It installs Windows programs and games, game stores (Epic, GOG, Battle.net…), game streaming and Deck add-ons, and adds them to Steam."
