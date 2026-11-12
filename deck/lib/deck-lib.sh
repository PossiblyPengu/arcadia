#!/usr/bin/env bash
# Shared helpers for the Steam Deck setup around Arcadia: config, logging, messages, Google Drive save sync, emulators, BIOS.
# Sourced by the event scripts and the tools; never run on its own.

DECK_HOME="${ARCADIA_HOME:-$HOME/Arcadia}"
DECK_CONF="${DECK_CONF:-$DECK_HOME/deck.conf}"
DECK_LOG="${DECK_LOG:-$DECK_HOME/logs/deck.log}"

# --- defaults, overridden by deck.conf -------------------------------------------------------------------------------
SYNC_REMOTE="gdrive:Arcadia"        # an rclone remote and folder; empty turns save sync off
SYNC_ENABLED=1
BIOS_DIR="$HOME/Emulation/bios"   # where BIOS files live (the EmuDeck layout; change it if yours differs)
SAVE_DIRS=()                      # empty = look for the usual save folders below
ROM_ROOT=""                       # empty = Arcadia's own ROM folder setting, else ~/Emulation/roms or ~/ROMs
INBOX="$HOME/Downloads"           # where new ROMs land, for "Sort downloads into ROM folders"
AUTO_SORT=0                       # 1 = sort the inbox into ROM folders each time Arcadia starts
APPIMAGE_PATH=""                  # where the Arcadia AppImage lives (for "Update Arcadia"); empty = the running one or ~/Applications

# deck_mark_done NAME / deck_is_done NAME: remember that a one-off setup step has been done (for the Setup checklist).
deck_mark_done() { mkdir -p "$DECK_HOME/state" 2>/dev/null && : > "$DECK_HOME/state/$1"; }
deck_is_done() { [ -f "$DECK_HOME/state/$1" ]; }

deck_rom_root() {
  local v="${ARCADIA_ROMS:-$ROM_ROOT}" settings="$DECK_HOME/settings/es_settings.xml"
  if [ -z "$v" ] && [ -f "$settings" ]; then v="$(sed -n 's/.*name="ROMDirectory" value="\([^"]*\)".*/\1/p' "$settings" | head -n 1)"; fi
  if [ -z "$v" ]; then if [ -d "$HOME/Emulation/roms" ]; then v="$HOME/Emulation/roms"; else v="$HOME/ROMs"; fi; fi
  v="${v/#\~/$HOME}"
  printf '%s\n' "${v%/}"
}

deck_load_conf() {
  mkdir -p "$(dirname "$DECK_LOG")" 2>/dev/null || true
  # shellcheck disable=SC1090
  [ -f "$DECK_CONF" ] && . "$DECK_CONF"
  if [ "${#SAVE_DIRS[@]}" -eq 0 ]; then
    local d
    for d in "$HOME/Emulation/saves" \
             "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/saves" \
             "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/states" \
             "$HOME/.config/retroarch/saves" "$HOME/.config/retroarch/states"; do
      [ -d "$d" ] && SAVE_DIRS+=("$d")
    done
  fi
  return 0
}

deck_log() {
  mkdir -p "$(dirname "$DECK_LOG")" 2>/dev/null || return 0
  if [ -f "$DECK_LOG" ] && [ "$(stat -c %s "$DECK_LOG" 2>/dev/null || echo 0)" -gt 1048576 ]; then mv -f "$DECK_LOG" "$DECK_LOG.old"; fi
  printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$DECK_LOG" 2>/dev/null || true
}

# deck_say TITLE TEXT: show a message the best way this machine can (a dialog, else a notification), and log it.
deck_say() {
  deck_log "$1: $2"
  # Run from Arcadia's SETUP menu: the app shows the text itself, so just print it.
  if [ "${ARCADIA_OUTPUT:-}" = stdout ]; then printf '%s\n' "$2"; return 0; fi
  [ "${DECK_QUIET:-}" = 1 ] && return 0
  if command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    zenity --info --title "$1" --text "$2" --width 420 2>/dev/null || true
  elif command -v kdialog >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    kdialog --title "$1" --msgbox "$2" 2>/dev/null || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "$1" "$2" 2>/dev/null || true
  else
    printf '%s\n%s\n' "$1" "$2"
  fi
}

# ---- save sync (rclone, to Google Drive or anything rclone supports) ---------------------------------------------------
# Nothing is ever deleted: files are copied only where they're newer, and a file that would be overwritten is kept first
# in ~/Arcadia/backups/sync (locally) or in a dated folder next to the saves on the remote.

_deck_key() { printf '%s' "${1#"$HOME"/}" | tr '/ ' '__'; }

# deck_sync pull|push
deck_sync() {
  local mode="$1" dir key stamp rc=0
  deck_load_conf
  [ "$SYNC_ENABLED" = 1 ] && [ -n "$SYNC_REMOTE" ] || return 0
  if ! command -v rclone >/dev/null 2>&1; then deck_log "save sync skipped: rclone isn't installed"; return 0; fi
  stamp="$(date +%Y%m%d-%H%M%S)"
  for dir in "${SAVE_DIRS[@]}"; do
    [ -d "$dir" ] || continue
    key="$(_deck_key "$dir")"
    local flags=(--update --contimeout 15s --timeout 60s --retries 1 --low-level-retries 1)
    if [ "$mode" = pull ]; then
      timeout 180 rclone copy "$SYNC_REMOTE/$key" "$dir" "${flags[@]}" --backup-dir "$DECK_HOME/backups/sync/$stamp/$key" >> "$DECK_LOG" 2>&1 || rc=$?
    else
      timeout 180 rclone copy "$dir" "$SYNC_REMOTE/$key" "${flags[@]}" --backup-dir "$SYNC_REMOTE/.backups/$stamp/$key" >> "$DECK_LOG" 2>&1 || rc=$?
    fi
  done
  if [ "$rc" -ne 0 ]; then deck_log "save sync ($mode) had a problem (rclone exit $rc); your saves were not touched beyond copying"; else deck_log "save sync ($mode) done"; fi
  return 0
}

# ---- emulators (Flatpak, which is what Arcadia finds on a Steam Deck) --------------------------------------------------
# name|flatpak id|systems
DECK_EMULATORS=(
  "RetroArch|org.libretro.RetroArch|most classic consoles"
  "DuckStation|org.duckstation.DuckStation|PlayStation"
  "PCSX2|net.pcsx2.PCSX2|PlayStation 2"
  "PPSSPP|org.ppsspp.PPSSPP|PSP"
  "Dolphin|org.DolphinEmu.dolphin-emu|GameCube and Wii"
  "melonDS|net.kuribo64.melonDS|Nintendo DS"
  "Azahar|org.azahar_emu.Azahar|Nintendo 3DS"
  "mGBA|io.mgba.mGBA|Game Boy Advance"
  "Flycast|org.flycast.Flycast|Dreamcast"
  "RPCS3|net.rpcs3.RPCS3|PlayStation 3"
  "Cemu|info.cemu.Cemu|Wii U"
  "xemu|app.xemu.xemu|Xbox"
)

# ---- Deckhand, the sister app (Windows programs, game stores, streaming, add-ons) --------------------------------------
DECKHAND_GET_URL="${DECKHAND_GET_URL:-https://raw.githubusercontent.com/PossiblyPengu/deckhand/main/get.sh}"
# deck_deckhand_bin: where Deckhand is installed (its get.sh puts it in ~/.local/bin), or nothing.
deck_deckhand_bin() {
  if [ -x "$HOME/.local/bin/deckhand" ]; then printf '%s\n' "$HOME/.local/bin/deckhand"; else command -v deckhand 2>/dev/null || true; fi
}
DECKHAND_BROKEN="$DECK_HOME/.deckhand-broken"  # its last launch failed: Setup reinstalls it
# deck_deckhand_ok: 1 if Deckhand is installed and its last launch from Setup didn't fail, else 0.
deck_deckhand_ok() { [ -n "$(deck_deckhand_bin)" ] && [ ! -e "$DECKHAND_BROKEN" ] && echo 1 || echo 0; }

deck_flatpak_installed() { flatpak info "$1" >/dev/null 2>&1; }

# ---- BIOS -------------------------------------------------------------------------------------------------------------
# system|label|required(1/0)|file names or patterns, separated by "/" (any one satisfies it)
DECK_BIOS=(
  "psx|PlayStation BIOS|1|scph5500.bin/scph5501.bin/scph5502.bin/scph1001.bin/scph7001.bin/scph7502.bin"
  "ps2|PlayStation 2 BIOS|1|scph*.bin/ps2-*.bin"
  "saturn|Saturn BIOS|1|sega_101.bin/mpr-17933.bin"
  "segacd|Sega CD BIOS|1|bios_CD_U.bin/bios_CD_E.bin/bios_CD_J.bin"
  "dreamcast|Dreamcast BIOS|1|dc_boot.bin"
  "dreamcast|Dreamcast flash|0|dc_flash.bin"
  "gba|GBA BIOS|0|gba_bios.bin"
  "nds|DS ARM7 BIOS|0|bios7.bin"
  "nds|DS ARM9 BIOS|0|bios9.bin"
  "nds|DS firmware|0|firmware.bin"
  "lynx|Lynx boot ROM|1|lynxboot.img"
  "pcengine|Super CD-ROM2 System Card|0|syscard3.pce"
  "atari7800|7800 BIOS|0|7800 BIOS (U).rom/7800 BIOS (E).rom"
  "switch|Switch keys|1|prod.keys"
  "xbox|Xbox MCPX boot ROM|1|mcpx_1.0.bin"
  "xbox|Xbox flash BIOS|1|Complex_4627v1.03.bin/Complex_4627.bin"
)

# deck_bios_find DIR PATTERN...: the first file under DIR (a few folders deep, any letter case) matching one pattern.
deck_bios_find() {
  local dir="$1" pat found
  shift
  for pat in "$@"; do
    found="$(find "$dir" -maxdepth 3 -type f -iname "$pat" 2>/dev/null | head -n 1)"
    [ -n "$found" ] && { printf '%s\n' "${found#"$dir"/}"; return 0; }
  done
  return 1
}

# deck_bios_report: one line per requirement, "ok|missing|optional TAB system TAB label TAB file"; returns 1 if a required file is missing.
deck_bios_report() {
  deck_load_conf
  local row sys label req names found rc=0
  local -a pats
  for row in "${DECK_BIOS[@]}"; do
    IFS='|' read -r sys label req names <<<"$row"
    IFS='/' read -r -a pats <<<"$names"
    if found="$(deck_bios_find "$BIOS_DIR" "${pats[@]}")"; then
      printf 'ok\t%s\t%s\t%s\n' "$sys" "$label" "$found"
    elif [ "$req" = 1 ]; then
      printf 'missing\t%s\t%s\t\n' "$sys" "$label"; rc=1
    else
      printf 'optional\t%s\t%s\t\n' "$sys" "$label"
    fi
  done
  return $rc
}
