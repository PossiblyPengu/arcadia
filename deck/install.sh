#!/usr/bin/env bash
# Set up the Steam Deck extras for Arcadia: cloud save sync, emulator install/update, BIOS check.
#
#   ./deck/install.sh             install (safe to run again)
#   ./deck/install.sh --uninstall remove what it added (your ROMs, saves and Arcadia settings are never touched)
#
# What it does, all inside your Arcadia folder (~/Arcadia) and ROM folder:
#   - copies the helper scripts to ~/Arcadia/deck
#   - links the event scripts into ~/Arcadia/scripts/{startup,game-start,game-end,quit}
#   - the tools are then used from Arcadia's own SETUP menu (main menu): get started, sort ROMs, emulators, BIOS,
#     controls, folder access, save sync, backup, updates
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
ESDE="${ARCADIA_HOME:-$HOME/Arcadia}"
TARGET="$ESDE/deck"
SYSTEMS="$ESDE/custom_systems/es_systems.xml"
SETTINGS="$ESDE/settings/es_settings.xml"
EVENTS=(startup game-start game-end quit)

rom_root() {
  local v=""
  [ -f "$SETTINGS" ] && v="$(sed -n 's/.*name="ROMDirectory" value="\([^"]*\)".*/\1/p' "$SETTINGS" | head -n 1)"
  [ -n "$v" ] || v="$HOME/ROMs"
  printf '%s\n' "${v/#\~/$HOME}"
}
ROMS="$(rom_root)/arcadia-setup"
BLOCK_START="<!-- arcadia-setup:begin -->"
BLOCK_END="<!-- arcadia-setup:end -->"

remove_block() {
  [ -f "$SYSTEMS" ] || return 0
  python3 - "$SYSTEMS" "$BLOCK_START" "$BLOCK_END" <<'PY' 2>/dev/null || sed -i "/$BLOCK_START/,/$BLOCK_END/d" "$SYSTEMS"
import sys,re
p,a,b=sys.argv[1:4]
s=open(p).read()
s=re.sub(re.escape(a)+r".*?"+re.escape(b)+r"\n?","",s,flags=re.S)
open(p,"w").write(s)
PY
}

if [ "${1:-}" = "--uninstall" ]; then
  for ev in "${EVENTS[@]}"; do rm -f "$ESDE/scripts/$ev"/arcadia-*.sh; done
  remove_block
  rm -rf "$TARGET" "$ROMS"
  echo "Removed the Steam Deck extras (your ROMs, saves and Arcadia settings were not touched)."
  exit 0
fi

mkdir -p "$TARGET" "$ESDE/logs"
rm -rf "$TARGET/lib" "$TARGET/tools"
cp -r "$HERE/lib" "$HERE/tools" "$TARGET/"
chmod +x "$TARGET"/lib/controls.py "$TARGET"/lib/emulators.py
# Arcadia's console list and where it looks for emulators: the emulator installer reads them to know what your games need.
if [ -d "$HERE/../resources/systems/linux" ]; then
  mkdir -p "$TARGET/lib/systems"
  cp "$HERE/../resources/systems/linux/es_systems.xml" "$HERE/../resources/systems/linux/es_find_rules.xml" "$TARGET/lib/systems/"
fi
chmod +x "$TARGET"/tools/*.sh

for ev in "${EVENTS[@]}"; do
  mkdir -p "$ESDE/scripts/$ev"
  for f in "$HERE/scripts/$ev"/arcadia-*.sh; do
    cp "$f" "$ESDE/scripts/$ev/"
    chmod +x "$ESDE/scripts/$ev/$(basename "$f")"
  done
done

if [ ! -f "$ESDE/deck.conf" ]; then
  cat > "$ESDE/deck.conf" <<CONF
# Settings for the Steam Deck extras. Lines starting with # are ignored.
# Cloud save sync uses rclone. Make a Google Drive remote once with:  rclone config   (name it "gdrive")
SYNC_ENABLED=1
SYNC_REMOTE="gdrive:Arcadia"      # leave empty to turn save sync off
# Folders whose files are synced. Empty = the usual EmuDeck / RetroArch Flatpak save folders that exist.
# SAVE_DIRS=("\$HOME/Emulation/saves")
# Where your BIOS files are (for "Check BIOS files").
BIOS_DIR="\$HOME/Emulation/bios"
# Where new ROMs land (for "Sort downloads into ROM folders"), and whether to sort them each time Arcadia starts.
INBOX="\$HOME/Downloads"
AUTO_SORT=0
# ROM_ROOT=""        # empty = Arcadia's ROM folder setting
# APPIMAGE_PATH=""   # where the Arcadia AppImage lives, for "Update Arcadia"
CONF
fi

# Older versions added a "Setup" system made of small scripts; the Setup menu inside Arcadia replaces it.
remove_block
rm -rf "$ROMS"

echo "Done."
echo "  • Event scripts: $ESDE/scripts/*/arcadia-*.sh   (custom event scripts are on by default in Arcadia)"
echo "  • Setup tools: open Arcadia's main menu and choose SETUP."
echo "  • Config: $ESDE/deck.conf  (set up rclone with a Google Drive remote called gdrive for save sync)"
