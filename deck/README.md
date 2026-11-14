# The setup tools (`deck/`)

These scripts do the work behind Arcadia's **SETUP** menu and the cloud save sync. They are plain Bash and Python, so they
can be tested and changed without rebuilding the program. To use them, see [`USERGUIDE.md`](../USERGUIDE.md).

## How the program uses them

- The program ships this folder (in the AppImage it is at `usr/share/arcadia/deck`). Each time SETUP opens, it runs
  `install.sh`, which copies `lib/` and `tools/` into `~/Arcadia/deck` and the event scripts into `~/Arcadia/scripts`.
  Installing is quick and safe to repeat, so the tools always match the program's version.
- A SETUP entry runs one tool with `ARCADIA_OUTPUT=stdout`, `ARCADIA_HOME` (the data folder) and `ARCADIA_ROMS` (the ROM
  directory) set. The tool prints its message, and the program shows it in a scrolling panel
  (`es-app/src/guis/GuiToolRunner.cpp`).
- Run anywhere else (a terminal, or a file manager), a tool shows its message in a zenity or kdialog dialog, or failing
  that a notification. Every message also goes to `~/Arcadia/logs/deck.log`.
- The event scripts (`scripts/<event>/arcadia-*.sh`) run through ES-DE's custom event scripts, which are on by default in
  Arcadia: save sync at startup, before and after a game and at quit, and the optional ROM sort at startup.

## What's here

| Path | What |
|---|---|
| `install.sh` | Installs the tools and event scripts into the data folder, writes `deck.conf` the first time, and removes the "Setup" game system that older versions added. `--uninstall` removes them again (never ROMs, saves or settings). |
| `lib/deck-lib.sh` | Shared settings, logging, messages, save sync (rclone), the emulator list and the BIOS list |
| `lib/romsort/` | The ROM sorter, ported from the earlier Arcadia app: headers, extensions, disc images, cue sheets, multi-disc playlists, Switch updates and DLC. Run with `python3 -m romsort --help`. |
| `lib/controls.py` | Starter controller settings for DuckStation, PCSX2 and RetroArch (Flatpak) |
| `lib/emulators.py` | What your games need (from your ROM folders and Arcadia's console list, which `install.sh` copies to `lib/systems/`), and installing it: Flatpak apps from Flathub and RetroArch cores from libretro's build server, checked against its published checksums. Behind Setup's Emulators screen (`es-app/src/guis/GuiEmulators.cpp`). |
| `lib/selfupdate.py` | Updates the AppImage and these tools from the project's GitHub releases |
| `tools/*.sh` | One script per SETUP entry |
| `scripts/` | The event scripts |
| `tests/test-deck.sh` | The tests |

## Settings (`~/Arcadia/deck.conf`)

| Setting | Default | Meaning |
|---|---|---|
| `SYNC_REMOTE` | `gdrive:Arcadia` | rclone remote and folder for saves; empty turns sync off |
| `SAVE_DIRS` | the EmuDeck and RetroArch save folders that exist | folders whose files are synced |
| `INBOX` | `~/Downloads` | where *Sort downloads into ROM folders* looks |
| `AUTO_SORT` | `0` | `1` sorts the inbox every time Arcadia starts |
| `BIOS_DIR` | `~/Emulation/bios` | where *Check BIOS files* looks |
| `ROM_ROOT` | the program's ROM directory | where sorted ROMs go, when the tools run outside the program |
| `APPIMAGE_PATH` | the running AppImage, else `~/Applications` | the AppImage *Update Arcadia* replaces |

Save sync only ever copies a file where it is newer, and keeps whatever it would replace (in `~/Arcadia/backups/sync`
locally, in `.backups/` on the remote). It never deletes or mirrors.

## Tests

`bash deck/tests/test-deck.sh` runs everything in a temporary home with stand-ins for `rclone` and `flatpak`, and a local
web server standing in for GitHub releases. The emulator controller settings follow each emulator's documented format but
haven't been run against the emulators themselves.

## Building the AppImage

`.github/workflows/steamdeck-appimage.yml` builds the Steam Deck AppImage on every push to `main` (download it from the
run's *Artifacts*). It also runs the setup tools' tests first.

**Releasing** works the same way as in Deckhand: bump the version in `VERSION`, write what changed in `RELEASE_NOTES.md`, and
push to `main`. If there is no release for that version yet, the workflow publishes `v<version>` with the AppImage and
`arcadia-deck-extras.tar.gz`, which is what *Update Arcadia* installs from. (Settings shows that version too.) Locally, `tools/create_AppImage_SteamDeck.sh` does the same.
