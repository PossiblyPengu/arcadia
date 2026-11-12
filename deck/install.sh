#!/usr/bin/env bash
# Set up the Steam Deck extras for ES-DE: cloud save sync, emulator install/update, BIOS check.
#
#   ./deck/install.sh             install (safe to run again)
#   ./deck/install.sh --uninstall remove what it added (your ROMs, saves and ES-DE settings are never touched)
#
# What it does, all inside your ES-DE folder (~/ES-DE) and ROM folder:
#   - copies the helper scripts to ~/ES-DE/deck
#   - links the event scripts into ~/ES-DE/scripts/{startup,game-start,game-end,quit}
#   - adds a "Setup" system to ES-DE (custom_systems/es_systems.xml) with entries you can pick with the controller:
#       Sync saves now, Install emulators, Update emulators, Check BIOS files, Set up emulator controls
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
ESDE="${ES_DE_HOME:-$HOME/ES-DE}"
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
  for ev in "${EVENTS[@]}"; do rm -f "$ESDE/scripts/$ev/arcadia-save-sync.sh"; done
  remove_block
  rm -rf "$TARGET" "$ROMS"
  echo "Removed the Steam Deck extras (your ROMs, saves and ES-DE settings were not touched)."
  exit 0
fi

mkdir -p "$TARGET" "$ESDE/logs"
rm -rf "$TARGET/lib" "$TARGET/tools"
cp -r "$HERE/lib" "$HERE/tools" "$TARGET/"
chmod +x "$TARGET"/lib/controls.py
chmod +x "$TARGET"/tools/*.sh

for ev in "${EVENTS[@]}"; do
  mkdir -p "$ESDE/scripts/$ev"
  cp "$HERE/scripts/$ev/arcadia-save-sync.sh" "$ESDE/scripts/$ev/arcadia-save-sync.sh"
  chmod +x "$ESDE/scripts/$ev/arcadia-save-sync.sh"
done

if [ ! -f "$ESDE/deck.conf" ]; then
  cat > "$ESDE/deck.conf" <<CONF
# Settings for the Steam Deck extras. Lines starting with # are ignored.
# Cloud save sync uses rclone. Make a Google Drive remote once with:  rclone config   (name it "gdrive")
SYNC_ENABLED=1
SYNC_REMOTE="gdrive:ES-DE"      # leave empty to turn save sync off
# Folders whose files are synced. Empty = the usual EmuDeck / RetroArch Flatpak save folders that exist.
# SAVE_DIRS=("\$HOME/Emulation/saves")
# Where your BIOS files are (for "Check BIOS files").
BIOS_DIR="\$HOME/Emulation/bios"
CONF
fi

# ES-DE's own "Setup" system: four entries, each a small script ES-DE launches like a game
mkdir -p "$ROMS"
mk_entry() { # file name, tool
  printf '#!/usr/bin/env bash\nexec "%s/tools/%s"\n' "$TARGET" "$2" > "$ROMS/$1"
  chmod +x "$ROMS/$1"
}
mk_entry "Sync saves now.sh" save-sync-now.sh
mk_entry "Install emulators.sh" install-emulators.sh
mk_entry "Update emulators.sh" update-emulators.sh
mk_entry "Check BIOS files.sh" check-bios.sh
mk_entry "Set up emulator controls.sh" setup-controls.sh

mkdir -p "$(dirname "$SYSTEMS")"
remove_block
if [ ! -f "$SYSTEMS" ]; then
  printf '<?xml version="1.0"?>\n<systemList>\n</systemList>\n' > "$SYSTEMS"
fi
python3 - "$SYSTEMS" "$BLOCK_START" "$BLOCK_END" <<'PY'
import sys
p,a,b=sys.argv[1:4]
block=f"""    {a}
    <system>
        <name>arcadia-setup</name>
        <fullname>Setup</fullname>
        <systemsortname>zzz-setup</systemsortname>
        <path>%ROMPATH%/arcadia-setup</path>
        <extension>.sh</extension>
        <command>/bin/bash %ROM%</command>
        <platform>pc</platform>
        <theme>arcadia-setup</theme>
    </system>
    {b}
"""
s=open(p).read()
i=s.rindex("</systemList>")
open(p,"w").write(s[:i]+block+s[i:])
PY

echo "Done."
echo "  • Event scripts: $ESDE/scripts/*/arcadia-save-sync.sh   (custom event scripts are on by default in this build;"
echo "    in stock ES-DE turn on Other settings > Enable custom event scripts)"
echo "  • Setup system: restart ES-DE and look for \"Setup\" in the system list."
echo "  • Config: $ESDE/deck.conf  (set up rclone with a Google Drive remote called gdrive for save sync)"
