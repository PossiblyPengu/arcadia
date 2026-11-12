# Steam Deck extras for this ES-DE fork

Everything here is plain scripts around ES-DE, installed with `./deck/install.sh` and removed with
`./deck/install.sh --uninstall`. Nothing touches your ROMs, saves or ES-DE settings.

## What you get

**Controls need no setup.** ES-DE reads controllers through SDL's standard gamepad layer, which is what a Steam Deck
presents in Game Mode, so the buttons work without a Steam layout.

**Windowed on the desktop, fullscreen in Game Mode.** This fork starts in a 1280x800 window on a desktop (including
the Deck's Desktop Mode) and fullscreen in Game Mode (it checks for gamescope / Steam). `--fullscreen` and `--windowed`
force one; `--resolution` still works as in stock ES-DE.

**Cloud save sync (rclone, Google Drive by default).** ES-DE's custom event scripts run `arcadia-save-sync.sh` at
startup and before a game (pull), and after a game and at quit (push). It only ever copies a file where it is newer and
keeps whatever it would overwrite (locally in `~/ES-DE/backups/sync`, on the remote in `.backups/`); it never deletes or
mirrors. Set it up once: `rclone config`, make a remote called `gdrive`, and check `~/ES-DE/deck.conf`. Custom event
scripts are on by default in this build.

**A "Setup" system inside ES-DE**, so you can do the chores with the controller: *Sync saves now*, *Install emulators*,
*Update emulators* (Flatpak, the same ones ES-DE finds on a Deck), *Check BIOS files* (names only; bring your own dumps),
*Set up emulator controls* (below).
Results show in a dialog (zenity or kdialog, else a notification) and in `~/ES-DE/logs/deck.log`.

**Starter emulator controls.** *Set up emulator controls* writes the Deck gamepad's buttons into DuckStation and PCSX2
(Flatpak) when they have no controller bindings yet, and sets RetroArch's hotkeys (hold Select: Start quits, X opens
the menu, the bumpers load / save a state) for keys that are still unset. Your own bindings are never overwritten, only
that controller section is touched, and the old file is copied to `~/ES-DE/backups/controls` first. Run
`deck/tools/setup-controls.sh --reset` to replace them with these. The setting names follow the emulators' documented
formats and haven't been run against the emulators themselves.

## Building the AppImage

`.github/workflows/steamdeck-appimage.yml` builds the Steam Deck AppImage (plus `arcadia-deck-extras.tar.gz`, this
folder) on GitHub: Actions tab > *Steam Deck AppImage* > Run workflow, or push a tag such as `v1.0.0` to also make a
release. Locally, `tools/create_AppImage_SteamDeck.sh` does the same on Ubuntu 22.04.

## Tests

`bash deck/tests/test-deck.sh` runs the scripts in a temporary home with a stand-in `rclone` and `flatpak`.
These haven't been run on a real Deck; the C++ change was built and started here under a virtual display.
