# Steam Deck extras for this Arcadia fork

Everything here is plain scripts around Arcadia, installed with `./deck/install.sh` and removed with
`./deck/install.sh --uninstall`. Nothing touches your ROMs, saves or Arcadia settings.

## What you get

**Controls need no setup.** Arcadia reads controllers through SDL's standard gamepad layer, which is what a Steam Deck
presents in Game Mode, so the buttons work without a Steam layout.

**Windowed on the desktop, fullscreen in Game Mode.** This fork starts in a 1280x800 window on a desktop (including
the Deck's Desktop Mode) and fullscreen in Game Mode (it checks for gamescope / Steam). `--fullscreen` and `--windowed`
force one; `--resolution` still works as in stock Arcadia.

**Cloud save sync (rclone, Google Drive by default).** Arcadia's custom event scripts run `arcadia-save-sync.sh` at
startup and before a game (pull), and after a game and at quit (push). It only ever copies a file where it is newer and
keeps whatever it would overwrite (locally in `~/Arcadia/backups/sync`, on the remote in `.backups/`); it never deletes or
mirrors. Set it up once: `rclone config`, make a remote called `gdrive`, and check `~/Arcadia/deck.conf`. Custom event
scripts are on by default in this build.

**A "Setup" system inside Arcadia**, so you can do the chores with the controller: *Sync saves now*, *Install emulators*,
*Update emulators* (Flatpak, the same ones Arcadia finds on a Deck), *Check BIOS files* (names only; bring your own dumps),
*Set up emulator controls* (below), plus the tools ported from Arcadia (below).
Results show in a dialog (zenity or kdialog, else a notification) and in `~/Arcadia/logs/deck.log`.

**Starter emulator controls.** *Set up emulator controls* writes the Deck gamepad's buttons into DuckStation and PCSX2
(Flatpak) when they have no controller bindings yet, and sets RetroArch's hotkeys (hold Select: Start quits, X opens
the menu, the bumpers load / save a state) for keys that are still unset. Your own bindings are never overwritten, only
that controller section is touched, and the old file is copied to `~/Arcadia/backups/controls` first. Run
`deck/tools/setup-controls.sh --reset` to replace them with these. The setting names follow the emulators' documented
formats and haven't been run against the emulators themselves.

## Ported from Arcadia

Things Arcadia doesn't do, brought over from the Arcadia app. All of them are entries in the Setup system:

- **Sort downloads into ROM folders**: looks at the file's header, extension and disc contents (the same sorter as
  Arcadia: iNES / GBA / N64 / Sega headers, PlayStation / GameCube / Wii / Saturn discs, cue sheets and their tracks,
  multi-disc games joined by an `.m3u`, Switch updates and DLC grouped with their game) and moves what it is sure of
  into the right folder under your ROM folder. Anything unclear is listed and left alone; nothing is ever overwritten
  or deleted. *Undo last ROM sort* puts the files back. Variants: include subfolders, or pick a folder with a dialog.
  Set `AUTO_SORT=1` in `~/Arcadia/deck.conf` to sort the inbox (`INBOX`, default `~/Downloads`) every time Arcadia starts.
- **Get started checklist**: what's ready (games, emulators, BIOS files, rclone and your Drive remote) and the next step.
- **Let emulators see ROM folders**: the Flatpak permission change that stops emulators saying a game "can't be found".
- **Back up settings** / **Restore latest backup**: Arcadia's settings, game lists (favorites, play counts), custom
  systems and collections, and `deck.conf`; a restore first backs up the current state. `backup.sh --saves` adds saves.
- **Update Arcadia**: updates this fork's AppImage and the deck extras from the project's GitHub releases (the old
  AppImage is kept as `.previous`). The upstream Arcadia updater is turned off in this build, because it would offer the
  stock Arcadia instead of this fork. `AppImage` location: the running one, else `~/Applications`, or `APPIMAGE_PATH`.

Not brought over: Arcadia's own library and interface (Arcadia has these), its console pictures and logo downloads
(Arcadia's themes cover that), save-state snapshots, and Delta sync (dropped earlier).

## Building the AppImage

`.github/workflows/steamdeck-appimage.yml` builds the Steam Deck AppImage (plus `arcadia-deck-extras.tar.gz`, this
folder) on GitHub: Actions tab > *Steam Deck AppImage* > Run workflow, or push a tag such as `v1.0.0` to also make a
release. Locally, `tools/create_AppImage_SteamDeck.sh` does the same on Ubuntu 22.04.

## Tests

`bash deck/tests/test-deck.sh` runs the scripts in a temporary home with a stand-in `rclone` and `flatpak`.
These haven't been run on a real Deck; the C++ change was built and started here under a virtual display.
