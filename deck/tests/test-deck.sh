#!/usr/bin/env bash
# Tests for the Steam Deck extras. Run: bash deck/tests/test-deck.sh   (uses a temporary HOME and fake rclone/flatpak)
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
fails=0
ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; fails=$((fails + 1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"; mkdir -p "$HOME" "$TMP/bin"
export ES_DE_HOME="$HOME/ES-DE" DECK_QUIET=1 PATH="$TMP/bin:$PATH"
cat > "$TMP/bin/rclone" <<'R'
#!/usr/bin/env bash
echo "$*" >> "$HOME/rclone.calls"
R
cat > "$TMP/bin/flatpak" <<'F'
#!/usr/bin/env bash
echo "$*" >> "$HOME/flatpak.calls"
case "$1" in info) grep -qw -- "$2" <<<"${FAKE_INSTALLED:-org.libretro.RetroArch}" && exit 0 || exit 1;; esac
exit 0
F
chmod +x "$TMP/bin/rclone" "$TMP/bin/flatpak"

echo "install"
bash "$HERE/install.sh" >/dev/null
bash "$HERE/install.sh" >/dev/null   # again: no duplicates
SYS="$ES_DE_HOME/custom_systems/es_systems.xml"
check "setup system added once" '[ "$(grep -c "<name>arcadia-setup</name>" "$SYS")" = 1 ]'
check "es_systems.xml is valid XML" 'python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse(sys.argv[1])" "$SYS"'
for ev in startup game-start game-end quit; do check "event script in $ev" '[ -x "$ES_DE_HOME/scripts/'$ev'/arcadia-save-sync.sh" ]'; done
check "five entries to pick" '[ "$(ls "$HOME/ROMs/arcadia-setup" | wc -l)" = 5 ]'
check "config written once and kept" '[ -f "$ES_DE_HOME/deck.conf" ] && echo "# mine" >> "$ES_DE_HOME/deck.conf" && bash "$HERE/install.sh" >/dev/null && grep -q "# mine" "$ES_DE_HOME/deck.conf"'
printf '<?xml version="1.0"?>\n<systemList>\n    <system><name>nes</name></system>\n</systemList>\n' > "$SYS"
bash "$HERE/install.sh" >/dev/null
check "an existing custom systems file keeps its systems" 'grep -q "<name>nes</name>" "$SYS" && grep -q "arcadia-setup" "$SYS"'

echo "save sync"
mkdir -p "$HOME/Emulation/saves"; echo x > "$HOME/Emulation/saves/a.sav"
for ev in startup game-start; do "$ES_DE_HOME/scripts/$ev/arcadia-save-sync.sh" a b c d; done
check "pull copies down with --update and a backup folder" 'grep -q "^copy gdrive:ES-DE/Emulation_saves $HOME/Emulation/saves --update" "$HOME/rclone.calls" && grep -q -- "--backup-dir $ES_DE_HOME/backups/sync/" "$HOME/rclone.calls"'
: > "$HOME/rclone.calls"
for ev in game-end quit; do "$ES_DE_HOME/scripts/$ev/arcadia-save-sync.sh"; done
check "push copies up, backing up what it replaces" 'grep -q "^copy $HOME/Emulation/saves gdrive:ES-DE/Emulation_saves --update" "$HOME/rclone.calls" && grep -q -- "--backup-dir gdrive:ES-DE/.backups/" "$HOME/rclone.calls"'
check "nothing is ever deleted or mirrored" '! grep -Eq "^(sync|delete|purge|move|bisync)" "$HOME/rclone.calls"'
: > "$HOME/rclone.calls"; sed -i 's/^SYNC_REMOTE=.*/SYNC_REMOTE=""/' "$ES_DE_HOME/deck.conf"
"$ES_DE_HOME/scripts/game-end/arcadia-save-sync.sh"
check "an empty remote turns sync off" '[ ! -s "$HOME/rclone.calls" ]'
sed -i 's/^SYNC_REMOTE=.*/SYNC_REMOTE="gdrive:ES-DE"/' "$ES_DE_HOME/deck.conf"
mv "$TMP/bin/rclone" "$TMP/bin/rclone.off"
check "no rclone is not an error" '"$ES_DE_HOME/scripts/game-end/arcadia-save-sync.sh"; [ $? = 0 ] && grep -q "rclone isn.t installed" "$ES_DE_HOME/logs/deck.log"'
mv "$TMP/bin/rclone.off" "$TMP/bin/rclone"

echo "BIOS"
mkdir -p "$HOME/Emulation/bios/sub"
bash "$HERE/tools/check-bios.sh"
check "missing BIOS files are listed" 'grep -q "BIOS check: Missing" "$ES_DE_HOME/logs/deck.log" && grep -q "PlayStation BIOS" "$ES_DE_HOME/logs/deck.log"'
touch "$HOME/Emulation/bios/SCPH5501.BIN" "$HOME/Emulation/bios/sub/dc_boot.bin"
. "$HERE/lib/deck-lib.sh"
report="$(deck_bios_report)"
check "files are found by name, any letter case, one folder down" 'grep -q "^ok.psx" <<<"$report" && grep -q "^ok.dreamcast.Dreamcast BIOS" <<<"$report"'
check "optional files don't count as missing" 'grep -q "^optional.gba" <<<"$report"'
touch "$HOME/Emulation/bios/scph10000.bin" "$HOME/Emulation/bios/sega_101.bin" "$HOME/Emulation/bios/bios_CD_U.bin" "$HOME/Emulation/bios/lynxboot.img" "$HOME/Emulation/bios/prod.keys" "$HOME/Emulation/bios/mcpx_1.0.bin" "$HOME/Emulation/bios/Complex_4627.bin"
check "all required present returns success" 'deck_bios_report >/dev/null'

echo "emulators"
bash "$HERE/tools/install-emulators.sh" duckstation PCSX2 >/dev/null
check "installs only what was asked, user-level, from flathub" 'grep -q "install --user -y --noninteractive flathub org.duckstation.DuckStation" "$HOME/flatpak.calls" && grep -q "net.pcsx2.PCSX2" "$HOME/flatpak.calls" && ! grep -q "install.*Dolphin" "$HOME/flatpak.calls"'
: > "$HOME/flatpak.calls"
bash "$HERE/tools/install-emulators.sh" retroarch >/dev/null
check "something already installed is skipped" '! grep -q "^install" "$HOME/flatpak.calls"'
bash "$HERE/tools/update-emulators.sh" >/dev/null
check "update only touches installed emulators" 'grep -q "^update --user -y --noninteractive org.libretro.RetroArch$" "$HOME/flatpak.calls"'

echo "emulator controls"
export FAKE_INSTALLED="org.duckstation.DuckStation net.pcsx2.PCSX2 org.libretro.RetroArch"
DS="$HOME/.var/app/org.duckstation.DuckStation/data/duckstation/settings.ini"
PX="$HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"
RA="$HOME/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"
mkdir -p "$(dirname "$DS")" "$(dirname "$RA")"
printf '[Main]\nSetupWizardIncomplete = false\n\n[GPU]\nRenderer = Vulkan\n' > "$DS"
printf 'video_fullscreen = "true"\ninput_exit_emulator_btn = "nul"\ninput_menu_toggle_btn = "9"\n' > "$RA"
bash "$HERE/tools/setup-controls.sh"
check "DuckStation gets a pad section and keeps its other settings" 'grep -q "^Cross = SDL-0/A" "$DS" && grep -q "Renderer = Vulkan" "$DS" && grep -q "SetupWizardIncomplete" "$DS" && [ "$(grep -c "^\[Pad1\]" "$DS")" = 1 ]'
check "PCSX2 settings are created in its own folder" 'grep -q "Type = DualShock2" "$PX" && grep -q "^Triangle = SDL-0/Y" "$PX"'
check "RetroArch hotkeys fill unset keys but keep ones you chose" 'grep -q "input_exit_emulator_btn = \"7\"" "$RA" && grep -q "input_menu_toggle_btn = \"9\"" "$RA" && grep -q "input_enable_hotkey_btn = \"6\"" "$RA"'
check "the old files were backed up first" '[ "$(ls "$ES_DE_HOME/backups/controls" | wc -l)" -ge 2 ]'
sed -i 's/^Cross = .*/Cross = Keyboard\/Z/' "$DS"
bash "$HERE/tools/setup-controls.sh"
check "your own bindings are kept on a normal run" 'grep -q "^Cross = Keyboard/Z" "$DS"'
bash "$HERE/tools/setup-controls.sh" --reset
check "reset replaces just the controller section" 'grep -q "^Cross = SDL-0/A" "$DS" && ! grep -q "Keyboard/Z" "$DS" && grep -q "Renderer = Vulkan" "$DS" && [ "$(grep -c "^\[Pad1\]" "$DS")" = 1 ]'
check "reset also sets RetroArch's keys" 'grep -q "input_menu_toggle_btn = \"2\"" "$RA"'
export FAKE_INSTALLED="none"
bash "$HERE/tools/setup-controls.sh"
check "nothing installed means nothing to do" 'grep -q "nothing to set up" "$ES_DE_HOME/logs/deck.log"'
export FAKE_INSTALLED="org.libretro.RetroArch"

echo "uninstall"
bash "$HERE/install.sh" --uninstall >/dev/null
check "uninstall removes the block, scripts and entries" '! grep -q arcadia-setup "$SYS" && [ ! -e "$ES_DE_HOME/scripts/game-end/arcadia-save-sync.sh" ] && [ ! -d "$HOME/ROMs/arcadia-setup" ]'
check "uninstall leaves the other systems and your saves" 'grep -q "<name>nes</name>" "$SYS" && [ -f "$HOME/Emulation/saves/a.sav" ]'

echo
if [ "$fails" = 0 ]; then echo "all passed"; else echo "$fails failed"; exit 1; fi
