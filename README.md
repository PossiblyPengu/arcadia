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
- Controller-friendly: keyboard navigation works, and Steam Input maps a Steam Deck to it.
  A gamepad can also be read directly through evdev if the `evdev` package is installed.

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
| Move           | Arrow keys       | D-pad                            |
| Launch         | Enter            | A                                |
| Back           | Esc              | B                                |
| Favorite       | Ctrl+D           | Y                                |
| Previous/next system | —          | Left / right bumper              |
| Search         | Ctrl+F           | —                                |
| Rescan         | Ctrl+R           | —                                |

## Tests

```bash
pytest
```

The tests cover scanning, title cleanup, the library database, launch command
building, save-state snapshots, metadata, and config round trips. They do not need a display.

## Layout

```
arcadia/
  config.py      settings and default systems
  scanner.py     ROM discovery and title cleanup
  library.py     SQLite store (games, favorites, sessions)
  launcher.py    launch template -> argument list
  savestates.py  snapshot / restore of per-game saves
  metadata.py    sidecar JSON and cover art
  gamepad.py     optional evdev controller input
  ui.py          Qt windows and dialogs
  main.py        entry point
tests/
  test_core.py
```
