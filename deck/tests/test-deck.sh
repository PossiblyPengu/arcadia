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
export ARCADIA_HOME="$HOME/Arcadia" DECK_QUIET=1 PATH="$TMP/bin:$PATH"
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
SYS="$ARCADIA_HOME/custom_systems/es_systems.xml"
mkdir -p "$(dirname "$SYS")" "$HOME/ROMs/arcadia-setup"; touch "$HOME/ROMs/arcadia-setup/Old entry.sh"
printf '<?xml version="1.0"?>\n<systemList>\n    <system><name>nes</name></system>\n    <!-- arcadia-setup:begin -->\n    <system><name>arcadia-setup</name></system>\n    <!-- arcadia-setup:end -->\n</systemList>\n' > "$SYS"
bash "$HERE/install.sh" >/dev/null
bash "$HERE/install.sh" >/dev/null   # again: nothing doubles up
check "install copies Arcadia's console list for the emulator installer" '[ -f "$ARCADIA_HOME/deck/lib/systems/es_systems.xml" ] && [ -f "$ARCADIA_HOME/deck/lib/systems/es_find_rules.xml" ]'
check "the old Setup system is removed, other systems are kept" '! grep -q arcadia-setup "$SYS" && grep -q "<name>nes</name>" "$SYS" && [ ! -d "$HOME/ROMs/arcadia-setup" ]'
check "es_systems.xml is still valid XML" 'python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse(sys.argv[1])" "$SYS"'
for ev in startup game-start game-end quit; do check "event script in $ev" '[ -x "$ARCADIA_HOME/scripts/'$ev'/arcadia-save-sync.sh" ]'; done
for t in get-started get-deckhand sort-roms install-emulators update-emulators check-bios setup-controls grant-access save-sync-now backup update-arcadia; do check "tool $t is installed" '[ -x "$ARCADIA_HOME/deck/tools/'$t'.sh" ]'; done
check "config written once and kept" '[ -f "$ARCADIA_HOME/deck.conf" ] && echo "# mine" >> "$ARCADIA_HOME/deck.conf" && bash "$HERE/install.sh" >/dev/null && grep -q "# mine" "$ARCADIA_HOME/deck.conf"'
out="$(ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-started.sh")"
check "run from Arcadia's Setup menu a tool prints its message instead of opening a dialog" '[[ "$out" == *"Games"* && "$out" == *"Emulators"* ]]'

echo "save sync"
mkdir -p "$HOME/Emulation/saves"; echo x > "$HOME/Emulation/saves/a.sav"
for ev in startup game-start; do "$ARCADIA_HOME/scripts/$ev/arcadia-save-sync.sh" a b c d; done
check "pull copies down with --update and a backup folder" 'grep -q "^copy gdrive:Arcadia/Emulation_saves $HOME/Emulation/saves --update" "$HOME/rclone.calls" && grep -q -- "--backup-dir $ARCADIA_HOME/backups/sync/" "$HOME/rclone.calls"'
: > "$HOME/rclone.calls"
for ev in game-end quit; do "$ARCADIA_HOME/scripts/$ev/arcadia-save-sync.sh"; done
check "push copies up, backing up what it replaces" 'grep -q "^copy $HOME/Emulation/saves gdrive:Arcadia/Emulation_saves --update" "$HOME/rclone.calls" && grep -q -- "--backup-dir gdrive:Arcadia/.backups/" "$HOME/rclone.calls"'
check "nothing is ever deleted or mirrored" '! grep -Eq "^(sync|delete|purge|move|bisync)" "$HOME/rclone.calls"'
: > "$HOME/rclone.calls"; sed -i 's/^SYNC_REMOTE=.*/SYNC_REMOTE=""/' "$ARCADIA_HOME/deck.conf"
"$ARCADIA_HOME/scripts/game-end/arcadia-save-sync.sh"
check "an empty remote turns sync off" '[ ! -s "$HOME/rclone.calls" ]'
sed -i 's/^SYNC_REMOTE=.*/SYNC_REMOTE="gdrive:Arcadia"/' "$ARCADIA_HOME/deck.conf"
mv "$TMP/bin/rclone" "$TMP/bin/rclone.off"
check "no rclone is not an error" '"$ARCADIA_HOME/scripts/game-end/arcadia-save-sync.sh"; [ $? = 0 ] && grep -q "rclone isn.t installed" "$ARCADIA_HOME/logs/deck.log"'
mv "$TMP/bin/rclone.off" "$TMP/bin/rclone"

echo "BIOS"
mkdir -p "$HOME/Emulation/bios/sub"
bash "$HERE/tools/check-bios.sh"
check "missing BIOS files are listed" 'grep -q "BIOS check: Missing" "$ARCADIA_HOME/logs/deck.log" && grep -q "PlayStation BIOS" "$ARCADIA_HOME/logs/deck.log"'
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

echo "emulators: what your games need"
EMU="$HERE/lib/emulators.py"
G="$TMP/games"; mkdir -p "$G"/{psx,snes,windows,nes}; touch "$G/psx/"{A,B}.chd "$G/snes/C.sfc" "$G/windows/D.exe" "$G/nes/notes.txt"
plan="$(FAKE_INSTALLED=none ARCADIA_ROMS="$G" python3 "$EMU" plan)"
check "games are matched to Arcadia's own default: RetroArch for PlayStation and SNES" 'grep -q "^emu|org.libretro.RetroArch|RetroArch|missing|1|for your Sony PlayStation (2 games), Nintendo SNES" <<<"$plan"'
check "an emulator your games don't use isn't marked as needed" 'grep -q "^emu|org.duckstation.DuckStation|DuckStation|missing|0|" <<<"$plan"'
check "a folder of only notes doesn't count as games" '! grep -q "Entertainment System" <<<"$plan"'
check "Windows games are pointed to Deckhand" 'grep -q "^none|Microsoft Windows|1|deckhand$" <<<"$plan"'
mkdir -p "$TMP/g2"/{ps3,switch,ports}; touch "$TMP/g2/ps3/A.ps3" "$TMP/g2/switch/B.nsp" "$TMP/g2/ports/C.sh"
plan2="$(FAKE_INSTALLED=none ARCADIA_ROMS="$TMP/g2" python3 "$EMU" plan)"
check "a shortcut-based default still needs its emulator (PlayStation 3: RPCS3)" 'grep -q "^emu|net.rpcs3.RPCS3|RPCS3|missing|1|for your Sony PlayStation 3" <<<"$plan2"'
check "a console whose emulator isn't on Flathub says which one Arcadia uses" 'grep -q "^none|Nintendo Switch|1|Eden$" <<<"$plan2"'
check "scripts and shortcuts (ports) need nothing installed" '! grep -q "Ports" <<<"$plan2" && ! grep -q "|1|For your.*Ports" <<<"$plan2"'
check "the needed ones come first" '[ "$(head -n 1 <<<"$plan" | cut -d"|" -f2)" = org.libretro.RetroArch ]'
# A stand-in for libretro's build server: two cores, and the checksums it publishes for them.
CS="$TMP/cores-srv"; mkdir -p "$CS"
python3 - "$CS" <<'PY'
import sys, zipfile, zlib, os
d = sys.argv[1]; lines = []
for core, body in (("mednafen_psx", b"\x7fELF psx core"), ("snes9x", b"\x7fELF snes core"), ("bad", b"\x7fELF tampered")):
    lib = f"{core}_libretro.so"
    with zipfile.ZipFile(os.path.join(d, lib + ".zip"), "w") as z:
        z.writestr(lib, body)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    if core == "bad":
        crc ^= 1  # published checksum doesn't match what is served
    lines.append(f"2026-11-12 {crc:08x} {lib}.zip")
open(os.path.join(d, ".index-extended"), "w").write("\n".join(lines) + "\n")
PY
CPORT=$((20000 + RANDOM % 20000))
(cd "$CS" && python3 -m http.server $CPORT --bind 127.0.0.1 >/dev/null 2>&1) & CSPID=$!
for _ in $(seq 50); do curl -s "http://127.0.0.1:$CPORT/.index-extended" >/dev/null 2>&1 && break; sleep 0.1; done
export ARCADIA_CORES_URL="http://127.0.0.1:$CPORT" ARCADIA_RETROARCH_CORES="$TMP/ra-cores"
: > "$HOME/flatpak.calls"
out="$(FAKE_INSTALLED=none ARCADIA_ROMS="$G" ROM_ROOT="$G" ARCADIA_OUTPUT=stdout bash "$HERE/tools/install-emulators.sh")"
check "with no names it installs what the games need: RetroArch, from Flathub, for this user" 'grep -q "^install --user -y --noninteractive flathub org.libretro.RetroArch$" "$HOME/flatpak.calls" && ! grep -q "^install.*DuckStation" "$HOME/flatpak.calls"'
check "the user-level Flathub source is added first (SteamOS only has the system one)" '[ "$(grep -n "^remote-add --user --if-not-exists flathub" "$HOME/flatpak.calls" | cut -d: -f1)" -lt "$(grep -n "^install" "$HOME/flatpak.calls" | cut -d: -f1)" ]'
check "the new emulator can see the ROM folder straight away" 'grep -q "^override --user --filesystem=$G.* org.libretro.RetroArch$" "$HOME/flatpak.calls"'
check "the cores the games need are put where RetroArch and Arcadia look" '[ "$(cat "$TMP/ra-cores/mednafen_psx_libretro.so")" = "$(printf "\x7fELF psx core")" ] && [ -f "$TMP/ra-cores/snes9x_libretro.so" ]'
check "progress is shown as it goes, and the end says what happened" 'grep -q "Installing RetroArch (1 of 1)" <<<"$out" && grep -q "✓ Sony PlayStation" <<<"$out" && grep -q "All done" <<<"$out"'
check "the checklist names what is missing" '[ "$(FAKE_INSTALLED=none ARCADIA_ROMS="$G" python3 "$EMU" status)" = "0|needs RetroArch" ]'
check "with everything in place the checklist step is done" '[ "$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" status | cut -d"|" -f1)" = 1 ]'
check "and the Emulators screen says RetroArch is ready" 'grep -q "^emu|org.libretro.RetroArch|RetroArch|ready|1|" <<<"$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" plan)"'
rm "$TMP/ra-cores/snes9x_libretro.so"
check "a missing core shows up even when RetroArch is installed (first, so it isn't cut off)" 'grep -q "^emu|org.libretro.RetroArch|RetroArch|cores|1|1 core to add · for your" <<<"$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" plan)"'
check "and the checklist says so" '[ "$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" status)" = "0|cores missing" ]'
mkdir -p "$G/bad"
mkdir -p "$ARCADIA_HOME/custom_systems"; cp "$ARCADIA_HOME/custom_systems/es_systems.xml" "$TMP/sys.bak" 2>/dev/null
printf '<?xml version="1.0"?>\n<systemList>\n<system><name>badsys</name><fullname>Tampered Console</fullname><path>%%ROMPATH%%/bad</path><extension>.bin</extension><command label="Bad">%%EMULATOR_RETROARCH%% -L %%CORE_RETROARCH%%/bad_libretro.so %%ROM%%</command><platform>x</platform><theme>x</theme></system>\n</systemList>\n' > "$ARCADIA_HOME/custom_systems/es_systems.xml"
touch "$G/bad/game.bin"
out="$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" install retroarch)"
check "your own custom systems count too" 'grep -q "Tampered Console" <<<"$out"'
check "a core that doesn't match libretro's published checksum is refused and not installed" 'grep -q "✗ Tampered Console: .*checksum" <<<"$out" && [ ! -e "$TMP/ra-cores/bad_libretro.so" ] && grep -q "✓ Nintendo SNES" <<<"$out"'
check "a failure is said at the end" 'grep -q "Not everything installed" <<<"$out"'
cp "$TMP/sys.bak" "$ARCADIA_HOME/custom_systems/es_systems.xml" 2>/dev/null || rm -f "$ARCADIA_HOME/custom_systems/es_systems.xml"
rm -f "$TMP/ra-cores/snes9x_libretro.so"
out="$(ARCADIA_CORES_URL="http://example.com/x" FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" python3 "$EMU" install retroarch)"
check "cores only come from libretro's server (or a local test server)" 'grep -q "refusing to download from http://example.com" <<<"$out" && [ ! -e "$TMP/ra-cores/snes9x_libretro.so" ]'
printf '\x7fELF old psx' > "$TMP/ra-cores/mednafen_psx_libretro.so"; printf '\x7fELF snes core' > "$TMP/ra-cores/snes9x_libretro.so"
out="$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" ARCADIA_OUTPUT=stdout bash "$HERE/tools/update-emulators.sh")"
check "updating refreshes a core with a newer build" 'grep -q "1 RetroArch core updated" <<<"$out" && [ "$(cat "$TMP/ra-cores/mednafen_psx_libretro.so")" = "$(printf "\x7fELF psx core")" ]'
: > "$HOME/flatpak.calls"
out="$(FAKE_INSTALLED=org.libretro.RetroArch ARCADIA_ROMS="$G" ARCADIA_OUTPUT=stdout bash "$HERE/tools/install-emulators.sh" --remove org.libretro.RetroArch)"
check "remove uninstalls just that one, for this user, and keeps games and saves" 'grep -q "^uninstall --user -y --noninteractive org.libretro.RetroArch$" "$HOME/flatpak.calls" && grep -q "games, saves and settings stay" <<<"$out" && [ -f "$G/psx/A.chd" ]'
out="$(FAKE_INSTALLED=none ARCADIA_ROMS="$G" python3 "$EMU" install duckstation)"
check "installing one your games don't use says what they still need" 'grep -q "Your games still need RetroArch" <<<"$out"'
out="$(FAKE_INSTALLED=none ARCADIA_ROMS="$TMP/empty" python3 "$EMU" install --needed)"
check "no games yet: nothing is installed, and it says why" 'grep -q "add some games first" <<<"$out"'
kill $CSPID 2>/dev/null; unset ARCADIA_CORES_URL ARCADIA_RETROARCH_CORES

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
check "the old files were backed up first" '[ "$(ls "$ARCADIA_HOME/backups/controls" | wc -l)" -ge 2 ]'
sed -i 's/^Cross = .*/Cross = Keyboard\/Z/' "$DS"
bash "$HERE/tools/setup-controls.sh"
check "your own bindings are kept on a normal run" 'grep -q "^Cross = Keyboard/Z" "$DS"'
bash "$HERE/tools/setup-controls.sh" --reset
check "reset replaces just the controller section" 'grep -q "^Cross = SDL-0/A" "$DS" && ! grep -q "Keyboard/Z" "$DS" && grep -q "Renderer = Vulkan" "$DS" && [ "$(grep -c "^\[Pad1\]" "$DS")" = 1 ]'
check "reset also sets RetroArch's keys" 'grep -q "input_menu_toggle_btn = \"2\"" "$RA"'
export FAKE_INSTALLED="none"
bash "$HERE/tools/setup-controls.sh"
check "nothing installed means nothing to do" 'grep -q "nothing to set up" "$ARCADIA_HOME/logs/deck.log"'
export FAKE_INSTALLED="org.libretro.RetroArch"

echo "sort ROMs"
export ROM_ROOT_TEST="$HOME/ROMs"
mkdir -p "$HOME/Downloads/sub"
printf 'NES\x1a\x02\x01' > "$HOME/Downloads/Contra.nes"
printf 'NES\x1a\x02\x01' > "$HOME/Downloads/sub/Deep.nes"
head -c 300 /dev/zero > "$HOME/Downloads/Mystery.gba"
echo hi > "$HOME/Downloads/readme.txt"
touch -d '1 hour ago' "$HOME"/Downloads/*.* "$HOME"/Downloads/sub/*
bash "$HERE/tools/sort-roms.sh"
check "the inbox is sorted into Arcadia folders by system" '[ -f "$HOME/ROMs/nes/Contra.nes" ] && [ -f "$HOME/ROMs/gba/Mystery.gba" ] && [ ! -e "$HOME/Downloads/Contra.nes" ]'
check "a ROM in a subfolder waits unless told to look deeper" '[ -f "$HOME/Downloads/sub/Deep.nes" ] && [ ! -e "$HOME/ROMs/nes/Deep.nes" ]'
check "other files are left alone" '[ -f "$HOME/Downloads/readme.txt" ]'
bash "$HERE/tools/sort-roms.sh" --deep
check "--deep also sorts the subfolders" '[ -f "$HOME/ROMs/nes/Deep.nes" ]'
bash "$HERE/tools/sort-roms.sh" --undo
check "undo puts the last sort back" '[ -f "$HOME/Downloads/sub/Deep.nes" ] && [ ! -e "$HOME/ROMs/nes/Deep.nes" ] && [ -f "$HOME/ROMs/nes/Contra.nes" ]'
printf 'NES\x1a\x02\x01' > "$HOME/Downloads/Auto.nes"; touch -d '1 hour ago' "$HOME/Downloads/Auto.nes"
"$ARCADIA_HOME/scripts/startup/arcadia-auto-sort.sh"
check "the startup hook leaves the inbox alone when AUTO_SORT is off" '[ -f "$HOME/Downloads/Auto.nes" ]'
echo 'AUTO_SORT=1' >> "$ARCADIA_HOME/deck.conf"
"$ARCADIA_HOME/scripts/startup/arcadia-auto-sort.sh"
check "the startup hook sorts when AUTO_SORT=1" '[ -f "$HOME/ROMs/nes/Auto.nes" ] && grep -q "auto sort" "$ARCADIA_HOME/logs/deck.log"'


echo "sort ROMs into the folder you already use"
SORTROOT="$TMP/alias-roms"; SORTIN="$TMP/alias-in"; SORTJ="$TMP/alias-journal.json"
sortone() {  # sortone <file name>: sort one file from a fresh inbox
  rm -rf "$SORTIN"; mkdir -p "$SORTIN"; head -c 300 /dev/zero > "$SORTIN/$1"
  touch -d '1 hour ago' "$SORTIN/$1"  # (the sorter leaves files that were just written: they may still be downloading)
  (cd "$HERE/lib" && python3 -m romsort --rom-root "$SORTROOT" --journal "$SORTJ" --from "$SORTIN" >/dev/null 2>&1)
}
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT/megadrive"; touch "$SORTROOT/megadrive/Old.md"
sortone "Sonic.md"
check "a Mega Drive game goes to the megadrive folder you already have" '[ -f "$SORTROOT/megadrive/Sonic.md" ] && [ ! -e "$SORTROOT/genesis" ]'
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT"
sortone "Sonic.md"
check "with neither folder it uses genesis (the default)" '[ -f "$SORTROOT/genesis/Sonic.md" ] && [ ! -e "$SORTROOT/megadrive" ]'
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT/genesis" "$SORTROOT/megadrive"; touch "$SORTROOT/genesis/a.md" "$SORTROOT/genesis/b.md" "$SORTROOT/megadrive/c.md"
sortone "New.md"
check "with both folders it uses the one with more games" '[ -f "$SORTROOT/genesis/New.md" ]'
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT/genesis" "$SORTROOT/megadrive"; touch "$SORTROOT/genesis/a.md" "$SORTROOT/megadrive/b.md" "$SORTROOT/megadrive/c.md"
sortone "New.md"
check "...whichever it is" '[ -f "$SORTROOT/megadrive/New.md" ]'
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT/tg16"
sortone "Bonk.pce"
check "other equivalent names work too (PC Engine / TG-16)" '[ -f "$SORTROOT/tg16/Bonk.pce" ] && [ ! -e "$SORTROOT/pcengine" ]'
rm -rf "$SORTROOT"; mkdir -p "$SORTROOT/megadrive"
sortone "Mario.nes"
check "systems without an alias are unaffected" '[ -f "$SORTROOT/nes/Mario.nes" ]'
sed -i '/^AUTO_SORT=1/d' "$ARCADIA_HOME/deck.conf"
. "$HERE/lib/deck-lib.sh"; deck_load_conf
check "the ROM folder comes from Arcadia's setting when there is one" 'mkdir -p "$ARCADIA_HOME/settings" && echo "<string name=\"ROMDirectory\" value=\"$HOME/MyGames\" />" > "$ARCADIA_HOME/settings/es_settings.xml" && [ "$(deck_rom_root)" = "$HOME/MyGames" ]'
rm -f "$ARCADIA_HOME/settings/es_settings.xml"

echo "backup"
mkdir -p "$ARCADIA_HOME/settings" "$ARCADIA_HOME/gamelists/nes"; echo "<settings/>" > "$ARCADIA_HOME/settings/es_settings.xml"; echo "<gameList/>" > "$ARCADIA_HOME/gamelists/nes/gamelist.xml"
bash "$HERE/tools/backup.sh"
check "a backup archive is made" 'ls "$ARCADIA_HOME"/backups/arcadia-backup-*.tar.gz >/dev/null 2>&1 && tar -tzf "$(ls -1t "$ARCADIA_HOME"/backups/arcadia-backup-*.tar.gz | head -n 1)" | grep -q "gamelists/nes/gamelist.xml"'
echo "<gameList>changed</gameList>" > "$ARCADIA_HOME/gamelists/nes/gamelist.xml"
bash "$HERE/tools/backup.sh" --restore
check "restore brings the old files back and keeps the current ones first" 'grep -q "^<gameList/>" "$ARCADIA_HOME/gamelists/nes/gamelist.xml" && ls "$ARCADIA_HOME"/backups/before-restore-*.tar.gz >/dev/null 2>&1'

echo "folder access"
export FAKE_INSTALLED="org.libretro.RetroArch org.duckstation.DuckStation"
: > "$HOME/flatpak.calls"; mkdir -p "$HOME/ROMs"
bash "$HERE/tools/grant-access.sh"
check "installed Flatpak emulators get the ROM folder, user-level" 'grep -q "^override --user --filesystem=$HOME/ROMs.* org.duckstation.DuckStation$" "$HOME/flatpak.calls" && grep -q "org.libretro.RetroArch$" "$HOME/flatpak.calls" && ! grep "^override" "$HOME/flatpak.calls" | grep -q "Dolphin"'
export FAKE_INSTALLED="org.libretro.RetroArch"

echo "get started"
bash "$HERE/tools/get-started.sh"
check "the checklist reports games, emulators and rclone" 'grep -q "Get started: Games" "$ARCADIA_HOME/logs/deck.log" && grep -q "Cloud saves" "$ARCADIA_HOME/logs/deck.log"'

echo "update Arcadia"
SRV="$TMP/srv"; mkdir -p "$SRV/dl" "$HOME/Applications"
printf 'NEW-APPIMAGE' > "$SRV/dl/Arcadia_x64_SteamDeck.AppImage"
mkdir -p "$TMP/pack/deck"; cp -r "$HERE/lib" "$HERE/tools" "$HERE/scripts" "$HERE/install.sh" "$TMP/pack/deck/"; tar -C "$TMP/pack" -czf "$SRV/dl/arcadia-deck-extras.tar.gz" deck
PORT=$((20000 + RANDOM % 20000))
publish_release() {  # publish_release <tag> [nodigest|nosize]: what GitHub's "latest release" would say about the files in $SRV/dl
  python3 - "$SRV" "$PORT" "$1" "${2:-}" <<'PY'
import hashlib,json,os,sys
d,port,tag,mode=sys.argv[1:5]
def a(n):
    f=f"{d}/dl/{n}"
    asset={"name":n,"size":0 if mode=="nosize" else os.path.getsize(f),"browser_download_url":f"http://127.0.0.1:{port}/dl/{n}"}
    if mode!="nodigest":
        asset["digest"]="sha256:"+hashlib.sha256(open(f,"rb").read()).hexdigest()
    return asset
json.dump({"tag_name":tag,"assets":[a("Arcadia_x64_SteamDeck.AppImage"),a("arcadia-deck-extras.tar.gz")]},open(f"{d}/latest","w"))
PY
}
publish_release v9.9.9
(cd "$SRV" && python3 -m http.server $PORT --bind 127.0.0.1 >/dev/null 2>&1) & SRVPID=$!
sleep 1
printf 'OLD-APPIMAGE' > "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage"
export DECK_RELEASE_API="http://127.0.0.1:$PORT/latest"
DECK_APPIMAGE="$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" bash "$HERE/tools/update-arcadia.sh" --check
check "check says a newer release exists without changing anything" 'grep -q "newer release is available: v9.9.9" "$ARCADIA_HOME/logs/deck.log" && grep -q OLD-APPIMAGE "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage"'
DECK_APPIMAGE="$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" bash "$HERE/tools/update-arcadia.sh"
check "update replaces the AppImage and keeps the old one" 'grep -q NEW-APPIMAGE "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" && grep -q OLD-APPIMAGE "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage.previous" && [ -x "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" ]'
check "it reinstalls the extras and records the version" '[ "$(cat "$ARCADIA_HOME/deck/version")" = v9.9.9 ] && [ -x "$ARCADIA_HOME/deck/tools/sort-roms.sh" ]'
DECK_APPIMAGE="$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" bash "$HERE/tools/update-arcadia.sh"
check "a second run says it's up to date" 'tail -n 1 "$ARCADIA_HOME/logs/deck.log" | grep -q "Already up to date"'

echo "update Arcadia: only what the release says it is"
UPD="DECK_APPIMAGE=$HOME/Applications/Arcadia_x64_SteamDeck.AppImage"
GOODIMG="$(cat "$SRV/dl/Arcadia_x64_SteamDeck.AppImage")"
publish_release v9.9.10
printf 'EVIL-APPIMAGE' > "$SRV/dl/Arcadia_x64_SteamDeck.AppImage"; cp "$SRV/dl/Arcadia_x64_SteamDeck.AppImage" "$TMP/evil.img"
publish_release v9.9.10 nosize  # (the size is not what is tested here: the checksum is)
python3 - "$SRV" <<'PY'
import hashlib,json,sys
d=sys.argv[1]; j=json.load(open(f"{d}/latest"))
for a in j["assets"]:  # the listed checksum is for the real file; the served file is different
    if a["name"].startswith("Arcadia_x64"): a["digest"]="sha256:"+hashlib.sha256(b"NEW-APPIMAGE").hexdigest()
json.dump(j,open(f"{d}/latest","w"))
PY
env $UPD bash "$HERE/tools/update-arcadia.sh"
check "a download that is not the listed file is refused" 'grep -q "Not updated" "$ARCADIA_HOME/logs/deck.log" && grep -q "checksum" "$ARCADIA_HOME/logs/deck.log"'
check "...and nothing was replaced or recorded" 'grep -q NEW-APPIMAGE "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" && ! grep -q EVIL "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" && [ "$(cat "$ARCADIA_HOME/deck/version")" = v9.9.9 ] && [ ! -e "$HOME/Applications/Arcadia_x64_SteamDeck.AppImage.new" ]'
printf 'NEW-APPIMAGE' > "$SRV/dl/Arcadia_x64_SteamDeck.AppImage"

# a tampered extras archive must not get to run anything
mkdir -p "$TMP/evilpack/deck"; printf '#!/bin/bash\ntouch "$HOME/PWNED"\n' > "$TMP/evilpack/deck/install.sh"
cp "$SRV/dl/arcadia-deck-extras.tar.gz" "$TMP/good-extras.tar.gz"
tar -C "$TMP/evilpack" -czf "$SRV/dl/arcadia-deck-extras.tar.gz" deck
publish_release v9.9.10 nosize
python3 - "$SRV" "$TMP/good-extras.tar.gz" <<'PY'
import hashlib,json,sys
d,good=sys.argv[1:3]; j=json.load(open(f"{d}/latest"))
for a in j["assets"]:
    if a["name"].startswith("arcadia-deck-extras"): a["digest"]="sha256:"+hashlib.sha256(open(good,"rb").read()).hexdigest()
json.dump(j,open(f"{d}/latest","w"))
PY
env $UPD bash "$HERE/tools/update-arcadia.sh"
check "a tampered extras archive is refused before anything in it runs" '[ ! -e "$HOME/PWNED" ] && grep -q "Not updated" "$ARCADIA_HOME/logs/deck.log" && [ "$(cat "$ARCADIA_HOME/deck/version")" = v9.9.9 ]'
cp "$TMP/good-extras.tar.gz" "$SRV/dl/arcadia-deck-extras.tar.gz"

publish_release v9.9.10 nodigest
env $UPD bash "$HERE/tools/update-arcadia.sh"
check "a release that lists no checksum is not used" 'grep -q "doesn.t list a checksum" "$ARCADIA_HOME/logs/deck.log" && [ "$(cat "$ARCADIA_HOME/deck/version")" = v9.9.9 ]'
publish_release v9.9.9  # (back to the real release for the checks that follow)
kill $SRVPID 2>/dev/null; pkill -f "http.server $PORT" 2>/dev/null
export DECK_RELEASE_API="http://127.0.0.1:1/latest"  # nothing listens there: an unreachable server (never the real GitHub)
DECK_APPIMAGE="$HOME/Applications/Arcadia_x64_SteamDeck.AppImage" bash "$HERE/tools/update-arcadia.sh" --check
check "an unreachable server is reported, not fatal" 'grep -q "Not updated" "$ARCADIA_HOME/logs/deck.log" || grep -q "Update Arcadia: Not updated" "$ARCADIA_HOME/logs/deck.log"'

echo "deckhand"
check "the checklist says Deckhand isn't installed yet" 'grep -q "^deckhand|0|Windows games|" <<<"$(ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-started.sh" --status)"'
cat > "$TMP/get.sh" <<'G'
#!/bin/bash
mkdir -p "$HOME/.local/bin"
printf '#!/bin/bash\necho opened >> "$HOME/deckhand.calls"\n' > "$HOME/.local/bin/deckhand"
chmod +x "$HOME/.local/bin/deckhand"
G
out="$(DECKHAND_GET_URL="file://$TMP/get.sh" ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-deckhand.sh")"
check "Deckhand is installed with its own installer, then opened" '[ -x "$HOME/.local/bin/deckhand" ] && [ "$(cat "$HOME/deckhand.calls")" = opened ] && [[ "$out" == *"Deckhand is installed"* ]]'
check "the checklist then counts it as done" 'grep -q "^deckhand|1|" <<<"$(ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-started.sh" --status)"'
out="$(DECKHAND_GET_URL="file://$TMP/nothing-here" ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-deckhand.sh")"
check "once installed it's just opened" '[ "$(wc -l < "$HOME/deckhand.calls")" = 2 ] && [[ "$out" != *"Deckhand is installed"* ]]'
printf '#!/bin/bash\nexit 3\n' > "$HOME/.local/bin/deckhand"
out="$(DECKHAND_GET_URL="file://$TMP/nothing-here" ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-deckhand.sh")"; rc=$?
check "a Deckhand that won't start is reported, not called closed" '[ "$rc" = 1 ] && [[ "$out" == *"didn"*"start properly"*"code 3"* ]]'
check "and the checklist offers it again" 'grep -q "^deckhand|0|" <<<"$(ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-started.sh" --status)"'
out="$(DECKHAND_GET_URL="file://$TMP/get.sh" ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-deckhand.sh")"
check "picking it again reinstalls it and opens it" '[[ "$out" == *"Deckhand is installed"* ]] && [ "$(wc -l < "$HOME/deckhand.calls")" = 3 ] && grep -q "^deckhand|1|" <<<"$(ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-started.sh" --status)"'
rm -rf "$HOME/.local/bin/deckhand"
DECKHAND_GET_URL="file://$TMP/nothing-here" ARCADIA_OUTPUT=stdout bash "$HERE/tools/get-deckhand.sh" >/dev/null; rc=$?
check "an installer that can't be fetched is reported" '[ "$rc" = 1 ] && grep -q "Deckhand couldn.t be installed" "$ARCADIA_HOME/logs/deck.log"'

echo "uninstall"
bash "$HERE/install.sh" --uninstall >/dev/null
check "uninstall removes the scripts and tools" '[ ! -e "$ARCADIA_HOME/scripts/game-end/arcadia-save-sync.sh" ] && [ ! -d "$ARCADIA_HOME/deck" ]'
check "uninstall leaves the other systems and your saves" 'grep -q "<name>nes</name>" "$SYS" && [ -f "$HOME/Emulation/saves/a.sav" ]'

echo
if [ "$fails" = 0 ]; then echo "all passed"; else echo "$fails failed"; exit 1; fi
