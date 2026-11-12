# Arcadia

A game launcher for the Steam Deck (and any Linux PC): browse your consoles and games with a controller, launch them in the
right emulator, keep your saves in the cloud, and set it all up from inside the app.

Arcadia is a full fork of [ES-DE](https://es-de.org) (MIT licence). It keeps ES-DE's engine (scanning, scraping, launching,
themes, controller input) and has its own look (`DESIGN.md`), its own defaults for the Deck, and its own setup tools.

- **Console ring and game shelf** with a design language of its own. `DESIGN.md`
- **Windowed on the desktop, full screen in Game Mode**, controller works with no Steam layout
- **Setup tools:** sort downloaded ROMs into the right folders (with undo), install and update emulators, check BIOS files,
  starter controller settings, cloud save sync (rclone / Google Drive), backup and restore, self-update. `deck/README.md`
- Linux and Steam Deck only

## Screenshots

Taken from the program itself at 1280x800 (the Deck's screen), with test games that have no art yet:

| | |
|---|---|
| ![Boot](docs/screenshots/boot.png) | ![Consoles](docs/screenshots/consoles.png) |
| ![Game shelf](docs/screenshots/games-shelf.png) | ![Game list](docs/screenshots/games-list.png) |
| ![Main menu](docs/screenshots/main-menu.png) | ![Setup](docs/screenshots/setup.png) |
| ![Get started](docs/screenshots/setup-checklist.png) | ![Sorting ROMs](docs/screenshots/setup-sort.png) |
| ![First start](docs/screenshots/first-start.png) | |

## Build

```bash
sudo apt install build-essential cmake gettext libharfbuzz-dev libicu-dev libsdl2-dev libavcodec-dev libavfilter-dev \
  libavformat-dev libavutil-dev libfreeimage-dev libfreetype6-dev libgit2-dev libcurl4-openssl-dev libpugixml-dev \
  libasound2-dev libbluetooth-dev libgl1-mesa-dev libpoppler-cpp-dev
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release . && ninja
./arcadia
```

The Steam Deck AppImage is built by `.github/workflows/steamdeck-appimage.yml` (or `tools/create_AppImage_SteamDeck.sh`).
After first start, run `./deck/install.sh` to add the setup tools.

## Documents

- `USERGUIDE.md` how to install and use Arcadia
- `DESIGN.md` the design language
- `FORK.md` what differs from ES-DE
- `deck/README.md` the setup tools behind the SETUP menu
- `docs/es-de/` ES-DE's own documents (user guide, install and theme guides, changelog), kept for reference

Arcadia is based on ES-DE by Leon Styhre and contributors; see `CREDITS.md` and `LICENSE`.
