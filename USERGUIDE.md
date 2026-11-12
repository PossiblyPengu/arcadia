# Arcadia user guide

Arcadia is a game launcher for the Steam Deck and other Linux PCs. You pick a console, then a game, and Arcadia starts it in
the right emulator. A SETUP menu handles the chores: sorting downloaded ROMs, installing emulators, checking BIOS files,
syncing saves and updating.

Arcadia is built on ES-DE. Anything this guide doesn't cover works as in ES-DE's own guide, kept in
[`docs/es-de/USERGUIDE.md`](docs/es-de/USERGUIDE.md).

## Contents

1. [Installing on a Steam Deck](#installing-on-a-steam-deck)
2. [First start](#first-start)
3. [Getting around](#getting-around)
4. [The SETUP menu](#the-setup-menu)
5. [Saves in the cloud](#saves-in-the-cloud)
6. [Emulators and BIOS files](#emulators-and-bios-files)
7. [Covers and game information](#covers-and-game-information)
8. [Look and feel](#look-and-feel)
9. [Where things are](#where-things-are)
10. [Updating](#updating)
11. [Starting Arcadia from the command line](#starting-arcadia-from-the-command-line)
12. [When something goes wrong](#when-something-goes-wrong)

## Installing on a Steam Deck

1. In Desktop Mode, download `Arcadia_x64_SteamDeck.AppImage` (from the project's GitHub releases, or from the
   *Artifacts* of the latest *Steam Deck AppImage* run in the Actions tab).
2. Put it in `~/Applications` and make it executable: right-click > Properties > Permissions > *Is executable*, or
   `chmod +x ~/Applications/Arcadia_x64_SteamDeck.AppImage`.
3. To use it in Game Mode, add it to Steam: Steam > *Add a Non-Steam Game* > browse to the AppImage. Keep Steam's
   default controller layout for it. Arcadia adds nothing to Steam by itself, and your games never appear in the Steam
   library.

Arcadia opens full screen in Game Mode and in a window on the desktop.

## First start

If Arcadia finds no games, it says so and shows where it looks for them (the ROM directory, `~/ROMs` unless you change
it). From that screen:

- **SETUP** opens the main menu with SETUP at the top. *Sort downloads into ROM folders* moves the ROMs in your
  Downloads folder into the right place.
- **CHANGE** sets a different ROM directory, for example `~/Emulation/roms` if you used EmuDeck.
- **CREATE** makes one folder per system inside the ROM directory, each with a note saying which files it takes.

Games go in a folder per system: `~/ROMs/snes/Super Metroid.sfc`, `~/ROMs/psx/Game.chd`, and so on.

## Getting around

Everything works with the controller.

| Button | On the console screen | On the game screen |
|---|---|---|
| D-pad / left stick | choose a console | choose a game |
| A | open the console | start the game |
| B | | back to the consoles |
| X | screensaver | the game's pictures and video |
| Y | | add to or remove from Favorites |
| L1 / R1 | | previous / next console |
| Menu (≡) | main menu | main menu |
| View (⧉) | | options for this list (sort, filter, jump to a letter) |

On a keyboard: arrows, Enter (A), Backspace (B), Delete (X), Insert (Y), Page Up / Page Down (L1 / R1), Escape (menu),
F1 (options).

## The SETUP menu

Open the main menu and choose **SETUP**. Each entry runs a tool and shows what it did.

| Entry | What it does |
|---|---|
| Get started checklist | What's ready (games, emulators, BIOS files, cloud saves) and what to do next |
| Sort downloads into ROM folders | Moves ROMs from your Downloads folder into the right system folders. It checks each file's header, extension and disc contents, keeps cue sheets with their tracks, joins multi-disc games with an `.m3u` playlist and groups Switch updates and DLC with their game. Anything it isn't sure about is listed and left alone. Nothing is overwritten or deleted. |
| Sort downloads and subfolders | The same, looking inside the folders in Downloads too |
| Undo last ROM sort | Puts the last sort's files back where they came from |
| Install emulators / Update emulators | Installs or updates the Flatpak emulators: RetroArch, DuckStation, PCSX2, PPSSPP, Dolphin, melonDS, Azahar, mGBA, Flycast, RPCS3, Cemu and xemu |
| Check BIOS files | Lists which BIOS files are present and which are missing (by file name only) |
| Set up emulator controls | Gives DuckStation and PCSX2 the Deck's buttons, and RetroArch its hotkeys (hold Select, then Start quits, X opens the menu, L1 / R1 load / save a state). Bindings you made yourself are kept. |
| Let emulators see ROM folders | Lets the Flatpak emulators read your ROM, BIOS and save folders |
| Sync saves now | Sends and fetches saves straight away (see below) |
| Back up settings / Restore latest backup | Settings, game lists (favorites, play counts), custom systems and collections. A restore backs up the current state first. |
| Update Arcadia | Updates Arcadia and these tools from the project's releases |

The tools' settings are in `~/Arcadia/deck.conf`: the Downloads folder to sort (`INBOX`), whether to sort it every
time Arcadia starts (`AUTO_SORT=1`), the BIOS folder (`BIOS_DIR`) and the cloud remote (`SYNC_REMOTE`).

## Saves in the cloud

Arcadia syncs saves with Google Drive (or anything else rclone can reach). It fetches your newest saves when it starts
and before a game, and sends them after a game and when it quits. A file is only copied where it is newer, and anything
it would replace is kept first in `~/Arcadia/backups/sync` (or in `.backups/` on the remote). Nothing is ever deleted.

To set it up once:

1. Install rclone, and in a terminal run `rclone config`. Create a Google Drive remote named `gdrive`.
2. Check `SYNC_REMOTE` in `~/Arcadia/deck.conf` (default `gdrive:Arcadia`).
3. Saves are taken from the usual EmuDeck and RetroArch save folders. List your own in `SAVE_DIRS` if yours are
   elsewhere.

*Get started checklist* shows whether rclone and the remote are ready.

## Emulators and BIOS files

Arcadia finds emulators installed as Flatpaks, which is how they're installed on a Deck. *Install emulators* installs
the usual ones. To change which emulator a system uses, go to *OTHER SETTINGS > ALTERNATIVE EMULATORS* in the main menu. For a
single game, use the View button > *EDIT THIS GAME'S METADATA* (after turning on *ENABLE ALTERNATIVE EMULATORS PER
GAME* in the same settings menu). BIOS files have to come from your own consoles. Put them in `~/Emulation/bios` (or the folder set as
`BIOS_DIR`), and use *Check BIOS files* to see what's missing.

## Covers and game information

Games show their name on a tile until they have art. Choose **SCRAPER** in the main menu to download covers,
screenshots, descriptions and more from ScreenScraper (a free account gives better results) or TheGamesDB.

## Look and feel

Arcadia's design language is in [`DESIGN.md`](DESIGN.md). In **UI SETTINGS**:

- **Theme variant:** *Cover shelf* (the default) or *Plain list* for big libraries.
- **Theme color scheme:** *Ink* (deep navy, the default), *OLED black* or *Paper* (light).
- **Menu color scheme** (in the same menu): *Ink*, *OLED black* or *Paper*.
- **Theme transitions:** *Slide* or *Fade*.

The other themes that come with ES-DE (Linear, Modern, Slate) are still there under *Theme*.

## Where things are

| What | Where |
|---|---|
| Arcadia's own files | `~/Arcadia` |
| Settings | `~/Arcadia/settings/es_settings.xml` |
| Game lists (favorites, play counts, game information) | `~/Arcadia/gamelists` |
| Downloaded covers and videos | `~/Arcadia/downloaded_media` |
| Setup tools and their settings | `~/Arcadia/deck`, `~/Arcadia/deck.conf` |
| Backups | `~/Arcadia/backups` |
| Logs | `~/Arcadia/logs/es_log.txt` (the program), `~/Arcadia/logs/deck.log` (the setup tools) |
| Your games | the ROM directory, `~/ROMs` by default |

## Updating

*SETUP > Update Arcadia* downloads the latest release and replaces the AppImage (the old one is kept next to it as
`.previous`). It needs a published release. Until the project publishes one, download a new AppImage from the Actions tab
instead.

## Starting Arcadia from the command line

```
Arcadia_x64_SteamDeck.AppImage [options]
  --fullscreen        always full screen
  --windowed          always a window
  --resolution W H    a window of this size
  --home DIR          keep everything in DIR instead of your home folder
  --help              all the options
```

## When something goes wrong

- **A game doesn't start:** the emulator probably isn't installed, or can't see the ROM folder. Run *Install emulators*,
  then *Let emulators see ROM folders*.
- **Games are missing:** check they are in the right system folder (*Get started checklist* shows the ROM directory), then
  restart Arcadia.
- **A tool's message cuts off:** the full text is in `~/Arcadia/logs/deck.log`.
- **Anything else:** look at the end of `~/Arcadia/logs/es_log.txt`.
