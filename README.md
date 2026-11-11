# Arcadia

A personal emulator launcher and ROM library manager for Linux and Steam Deck,
written in Python with PySide6 (Qt).

## Features

- Scans per-system ROM folders and cleans up titles (region and revision tags removed)
- Library database with favorites, play counts, total playtime, and last played
- Launch games through any emulator via a command template per system
- Playtime is recorded per session, and it survives drives being unplugged
- Save-state snapshots: copy a game's saves into a snapshot, restore any snapshot later
  (the current saves are backed up automatically before a restore)
- Covers and metadata from an optional media folder (sidecar files, see below)
- Cover-flow shelf with reflections: the selected game sits large in a glowing ring, its
  neighbors shrink and fade, and the whole window takes on the current system's color
- System pills across the top (systems with no games are hidden), plus virtual
  **Recently played** and **Favorites** views that span every system
- Sort by A–Z, recently played, most played, or favorites first (remembered between runs)
- Type a letter to jump to the next title starting with it; search with Ctrl+F
- Toast messages instead of dialogs, a live play timer on the Launch button, and a
  fullscreen mode for the couch (`python -m arcadia --fullscreen` or F11)
- Covers load lazily, so large libraries stay fast
- **Multi-disc games** become one library entry (an `.m3u` playlist), and **games with updates and
  DLC** (Nintendo Switch) show as one game with its update and DLC files attached
- **ROM sorting**: point Arcadia at your downloads folder and it moves each ROM into the
  right system folder, asking you whenever it isn't sure (see below)
- Presets for Nintendo (NES, SNES, Game Boy, Game Boy Color, GBA, N64, Switch), Sega (Genesis,
  Master System, Game Gear), and PlayStation / PSP, using standalone Flatpak emulators
  where they exist and RetroArch otherwise
- "Surprise me" picks a random game from the current system
- Controller-friendly: keyboard navigation works, and Steam Input maps a Steam Deck to it.
  A gamepad can also be read directly through evdev if the `evdev` package is installed.

## Sorting ROMs from your downloads folder

Set **Downloads folder (ROM inbox)** in File → Settings (or just choose File → Import ROMs…,
which asks for it). Arcadia then watches that folder and decides which system each file belongs to
using, strongest first:

1. **The file's header**: iNES (NES), the Game Boy / Game Boy Color / GBA logos, N64 byte-order
   markers, Sega Mega Drive / Master System / Game Gear headers, the SNES header checksum, PSP and
   PlayStation disc markers, and what's inside a PBP. Zip files are opened and the ROM inside is checked.
2. **The extension** (`.sfc`, `.gba`, `.cso`, ...).
3. **The name**, used only as a hint (`(GBC)`, `Super Nintendo`, `Mega Drive`, ...).

Each file gets a confidence:

| Confidence | Meaning | What happens |
|------------|---------|--------------|
| ✓ certain  | The header confirms the extension | Moved automatically (turn this off in Settings to always ask) |
| ~ likely   | The extension is clear but the header couldn't be verified | Listed, pre-ticked, for you to confirm |
| ? unsure   | Ambiguous or contradictory: a `.gbc` with a Game Boy header, a `.chd` that could be PlayStation or PSP, a zip holding several ROMs, a `.7z` | Listed, **not** ticked. Pick the system and tick it to move it |

Safety rules:

- Nothing is ever overwritten. If a file with that name is already in the library it is skipped
  (or, if you tick "keep both", the new one is renamed `Name (2).ext`).
- Files still being downloaded (`.crdownload`, `.part`, or modified in the last few seconds) are left alone.
- Files that don't look like ROMs are never touched.
- A game that's running is never interrupted by the dialog; Arcadia asks once it's over.
- Every move is recorded: **File → Undo last import** puts the files back where they came from.
- Moves across drives are copied, size-checked, and only then removed from the downloads folder.
- Cue sheets move together with the `.bin` tracks they list.

Limits: `.7z` and `.rar` archives can't be inspected (they're only offered if the name mentions a
system), `.chd` and `.cue` images can't be fully verified, multi-disc `.m3u` playlists aren't handled, and
a zip is moved as one file rather than extracted, so a zip of 50 ROMs is treated as one game.

## Multi-disc games

A multi-disc game is one entry in the library, backed by an `.m3u` playlist that lists its discs.
RetroArch and DuckStation load the playlist directly and let you swap discs in the emulator.

```
psx/Final Fantasy VII (USA).m3u        <- this is the game in Arcadia
psx/Final Fantasy VII (USA)/           <- its discs live here and are hidden
    Final Fantasy VII (USA) (Disc 1).cue / .bin
    Final Fantasy VII (USA) (Disc 2).cue / .bin
```

- **From the downloads folder**, discs are recognised by tags like `(Disc 1)`, `(Disc 2 of 3)`, `[Disc A]`,
  `(CD2)`, or `Disc 3` in the name, grouped by game and region, and joined automatically when the
  header checks are certain. Discs of different regions or revisions are never mixed.
- **A missing disc asks you first**: if `(Disc 1)` and `(Disc 3)` arrive, or `(Disc 1 of 3)` has no
  disc 2, the set is shown unticked with the reason, and nothing moves until you confirm.
- **A disc arriving later** (say disc 2 a week after disc 1) is added to the existing playlist.
- **Making your own playlist** works too: put an `.m3u` next to your discs and Arcadia hides the
  discs and moves their favorite flag and playtime onto the playlist.
- Undo (File → Undo last import) removes the playlist and folder it made, or restores an edited playlist.

Limits: a lone disc with no playlist yet is moved as an ordinary game (with a note that it looks like
a disc), and discs already sitting loose in your library aren't reorganised for you. PPSSPP can't open
playlists, so multi-disc PSP games need their discs launched individually.

## Games with updates and DLC (Nintendo Switch)

Switch files carry a title ID in their name (`Game [0100ABCD00012000][v0].nsp`), and the ID says what a file is:
a base game ends in `000`, its update in `800`, and its DLC lives in the next ID block up. Arcadia uses that
to attach updates and DLC to their base game, so the library shows **one game**, not one entry per file.

- The details line shows what's attached ("1 update (latest v65536), 2 DLC"), and **Files…** lists every file
  with its size and opens the folder.
- From the downloads folder, a game and the updates and DLC that arrived with it move together.
- An update or DLC with no base game is shown on its own, labelled `(update)` or `(DLC)`, and can't be
  launched (there's nothing to run). It attaches itself as soon as the base game turns up. An update
  arriving for a game that isn't in your library yet is flagged so you can decide.
- Files are stored side by side in the `switch` folder, as most emulators expect.

**What Arcadia does not do:** it can't make an emulator apply an update. Ryujinx and similar emulators
install updates and DLC through their own menus, and I haven't verified a command-line way to pass them,
so the Ryujinx preset launches the base game only. If your emulator does take them on the command line,
use the placeholders in the launch command (Settings): `{rom}` the game, `{updates}` update files,
`{dlc}` DLC files, `{discs}` a multi-disc game's discs, e.g. `myemu --update {updates} --dlc {dlc} {rom}`.
A placeholder with nothing to fill it disappears, and every path is quoted.

Other limits: linking depends on the `[title ID]` in the file name, as in most dumps (the files' contents are
encrypted), so a file without one is treated as a game of its own. A DLC whose ID ends in `800` would be
mistaken for an update.

## Presets and Flatpak access

Launch commands default to the presets in `arcadia/presets.py` (Switch uses Ryujinx from the Ryubing
fork, Flathub `io.github.ryubing.Ryujinx`; Eden, `dev.eden_emu.eden`, is the other Flathub option). Their Flatpak IDs were
checked on Flathub. The command-line options and save folders are the usual defaults and
should be checked on your machine. Settings → "Reset launch commands to presets" restores them.

Flatpak apps can only read folders they've been granted, so grant your ROM folder once per app:

```bash
flatpak override --user --filesystem=/path/to/ROMs org.libretro.RetroArch
flatpak override --user --filesystem=/path/to/ROMs io.mgba.mGBA
flatpak override --user --filesystem=/path/to/ROMs com.snes9x.Snes9x
flatpak override --user --filesystem=/path/to/ROMs org.duckstation.DuckStation
flatpak override --user --filesystem=/path/to/ROMs org.ppsspp.PPSSPP
flatpak override --user --filesystem=/path/to/ROMs io.github.ryubing.Ryujinx
```

Save-state snapshots only work where the save folder is set. Standalone presets
(mGBA, Snes9x, DuckStation, PPSSPP) have no save folder set by default, because the
exact location depends on the emulator's configuration. Set it in Settings if you want snapshots.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m arcadia
```

## Configuration

Settings are stored in `~/.config/arcadia/config.json` and can be edited in the
Settings dialog (File > Settings). The library database is in
`~/.local/share/arcadia/library.db`.

For each system you set:

- **ROM folder**: the folder name under the ROM root, e.g. `snes`
- **Extensions**: which files count as games, e.g. `.sfc, .smc, .zip`
- **Launch command**: a command with `{rom}` where the ROM path goes, e.g.
  `retroarch -L /path/to/core.so {rom}` or `flatpak run org.libretro.RetroArch -L core.so {rom}`
- **Emulator save folder**: where that emulator keeps its saves, used for save states

Save states copy the files in the save folder whose names start with the ROM name
and a dot (`Game.srm`, `Game.state1`, ...). Emulators that store saves per-game
in a different layout will need their save folder configured to match.

## Optional metadata

Put files in the media folder (default `~/.local/share/arcadia/media`):

```
media/snes/Super Mario World.json   {"title": "...", "description": "...", "year": "1990", "genre": "Platform"}
media/snes/Super Mario World.png    cover art (png, jpg, jpeg, webp)
```

## Controls

| Action         | Keyboard         | Controller (evdev / Steam Input) |
|----------------|------------------|----------------------------------|
| Browse         | Left / Right     | D-pad left / right               |
| Jump to system bar | Up           | D-pad up (down returns to the shelf) |
| Jump to letter | Type a letter    | —                                |
| Fullscreen     | F11              | —                                |
| Launch         | Enter            | A                                |
| Back           | Esc              | B                                |
| Favorite       | Ctrl+D           | Y                                |
| Previous/next system | —          | Left / right bumper              |
| Surprise me    | —                | —                                |
| Search         | Ctrl+F           | —                                |
| Rescan         | Ctrl+R           | —                                |

## Tests

```bash
pytest
```

The tests cover scanning, title cleanup, the library database, launch command
building, save-state snapshots, metadata, config round trips, and the window itself
(run headlessly with Qt's offscreen platform, so no display is needed).

## Layout

```
arcadia/
  config.py      settings and default systems
  scanner.py     ROM discovery and title cleanup
  sorter.py      identify ROMs in the downloads folder and move them safely, with undo
  bundles.py     disc tags, playlists, and Switch title IDs
  files_dialog.py  every file that makes up a game
  import_dialog.py  the confirm-before-moving dialog
  library.py     SQLite store (games, favorites, sessions)
  launcher.py    launch template -> argument list
  savestates.py  snapshot / restore of per-game saves
  metadata.py    sidecar JSON and cover art
  presets.py     launch presets and system accent colors
  theme.py       stylesheet, animated backdrop, toast messages
  coverflow.py   animated cover-flow carousel with lazy cover loading
  gamepad.py     optional evdev controller input
  ui.py          Qt windows and dialogs
  main.py        entry point
tests/
  test_core.py   scanning, library, launching, save states, config
  test_sorter.py ROM identification, plans, safe moves, and undo
  test_bundles.py  disc-name, playlist, and title-ID parsing
  test_multifile.py  multi-disc sets and update/DLC bundles end to end
  test_ui.py     window, cover flow, and import dialog tests (skipped where Qt can't load)
```
