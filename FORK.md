# This fork

A fork of [ES-DE](https://es-de.org) (MIT licence, see LICENSE and CREDITS.md) for the Steam Deck. The changes are kept small
and separate so upstream updates stay easy to merge:

- `es-app/src/main.cpp`: `--fullscreen` / `--windowed`, windowed on a desktop and fullscreen in Game Mode by default.
- `es-core/src/Settings.cpp`: custom event scripts on by default.
- `deck/`: save sync, emulator install/update, BIOS check and the "Setup" system. See `deck/README.md`.
