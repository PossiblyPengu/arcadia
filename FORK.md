# This fork

A fork of [ES-DE](https://es-de.org) (MIT licence, see LICENSE and CREDITS.md) for the Steam Deck. The changes are kept small
and separate so upstream updates stay easy to merge:

- `es-app/src/main.cpp`: `--fullscreen` / `--windowed`, windowed on a desktop and fullscreen in Game Mode by default.
- `es-core/src/Settings.cpp`: custom event scripts on by default.
- `deck/`: save sync, emulator install/update, BIOS check and the "Setup" system. See `deck/README.md`.
- `themes/linear-es-de` and `themes/modern-es-de`: an "Arcadia" colour scheme (deep navy, blue accent), first in the list so it is the default. Choose another under UI settings > Theme set options > Color scheme.
- `themes/linear-es-de`: the console carousel dims the consoles you're not on, so the selected one stands out.
- `.github/workflows/steamdeck-appimage.yml`: builds the Steam Deck AppImage and the deck extras.
- `CMakeLists.txt`: the upstream application updater is off by default (it would replace the fork with stock ES-DE); use the deck's *Update ES-DE* instead.
- `deck/lib/romsort/`: the ROM sorter from Arcadia, as a command line tool.
- Trimmed to Linux and the Steam Deck: the Android, macOS, Windows, Haiku, iOS, web and BSD code and files were removed (they stay in git history). The `--no-update-check` option went with the upstream updater.
- Menus and dialogs use the Arcadia colour schemes (ink, oled, paper) and a white focus ring, see `DESIGN.md`.
- Renamed to Arcadia (binary, folder `~/Arcadia`, app ID `io.github.PossiblyPengu.Arcadia`). The ScreenScraper account name stays "ES-DE" because
  that service registers software by name.
- A native **SETUP** screen at the top of the main menu runs the deck tools (get started, sort ROMs, emulators, BIOS, controls, folder
  access, saves, backup, update) and shows what they say. The no-games dialog at first start points to it.
- Build files are Linux only; the program ships its `deck/` folder and installs the tools into the data folder when SETUP opens.
- Button hints are shorter (the game screen shows six instead of eight), the empty screen behind dialogs is the ink colour instead of black,
  the boot screen and window icon are Arcadia's, and the screensaver dims by default.
- Documents: `USERGUIDE.md` is Arcadia's own guide; ES-DE's documents moved to `docs/es-de/`.
