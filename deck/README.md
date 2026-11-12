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
*Update emulators* (Flatpak, the same ones ES-DE finds on a Deck), *Check BIOS files* (names only; bring your own dumps).
Results show in a dialog (zenity or kdialog, else a notification) and in `~/ES-DE/logs/deck.log`.

## Tests

`bash deck/tests/test-deck.sh` runs the scripts in a temporary home with a stand-in `rclone` and `flatpak`.
These haven't been run on a real Deck; the C++ change was built and started here under a virtual display.
