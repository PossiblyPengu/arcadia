#!/usr/bin/env bash
# Which BIOS files are present, and which are missing (names only: it can't tell whether a dump is good).
. "$(dirname "$(readlink -f "$0")")/../lib/deck-lib.sh"
report="$(deck_bios_report)"; rc=$?
missing="$(printf '%s\n' "$report" | awk -F'\t' '$1=="missing"{printf "  • %s (%s)\n",$3,$2}')"
optional="$(printf '%s\n' "$report" | awk -F'\t' '$1=="optional"{n++} END{print n+0}')"
found="$(printf '%s\n' "$report" | awk -F'\t' '$1=="ok"{n++} END{print n+0}')"
if [ "$rc" -eq 0 ]; then
  deck_say "BIOS check" "All required BIOS files are in $BIOS_DIR ($found found, $optional optional ones absent). Arcadia can't supply BIOS files; bring your own dumps."
else
  deck_say "BIOS check" "Missing in $BIOS_DIR:"$'\n'"$missing"$'\n\n'"$found found. Bring your own dumps; only the file names are checked."
fi
