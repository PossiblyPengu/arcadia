# This fork

A fork of [ES-DE](https://es-de.org) (MIT licence, see LICENSE and CREDITS.md) for the Steam Deck. The changes are kept small
and separate so upstream updates stay easy to merge:

- `es-app/src/main.cpp`: `--fullscreen` / `--windowed`, windowed on a desktop and fullscreen in Game Mode by default.
- `es-core/src/Settings.cpp`: custom event scripts on by default.
- `deck/`: save sync, emulator install/update, BIOS check and the "Setup" system. See `deck/README.md`.
- `themes/linear-es-de` and `themes/modern-es-de`: an "Arcadia" colour scheme (deep navy, blue accent), first in the list so it is the default. Choose another under UI settings > Theme set options > Color scheme.
- `themes/linear-es-de`: the console carousel dims the consoles you're not on, so the selected one stands out.
- `.github/workflows/steamdeck-appimage.yml`: builds the Steam Deck AppImage and the deck extras.
