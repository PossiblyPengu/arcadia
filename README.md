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
- **Two screens: choose a console, then choose a game.** The first screen is a **rotating carousel of pixel-art
  consoles**: the selected one sits large in the middle with its name and game count, the others curve away on both
  sides, and the ring wraps around (after the last comes the first). Hover any console and it glows. Consoles with no
  games are hidden; **Recently played**, **Favorites** and **All games** are on the ring too. Open the middle one to
  get that console's cover-flow shelf, and go back with Esc / B / the "Consoles" button. Ctrl+F from the console
  screen searches every game. Moving between the two screens is a short zoom (the screen you leave swells or
  shrinks away over the new one).
- **Sound effects** (View → Sound effects, on by default): a soft tick as the console ring turns, a chime on opening
  a console, a falling tone on going back. They are tiny generated tones (`assets/sounds`, made by
  `tools/make_sounds.py`); with no audio device, or with the setting off, nothing plays and nothing breaks.
- **Each console is shown in the pixel style of its own generation, and the screen says which** (8-BIT, 16-BIT,
  32-BIT, 64-BIT, 128-BIT, HD, under the console's name). Which generation a console belongs to is `arcadia/eras.py`.
  There are two sets of pictures, switched under View → Pictures:
  - **Console logos** (the default): View → Pictures → *Download console logos…* fetches each console's logo from
    Wikipedia / Wikimedia Commons into your own `media/logos` folder (they're the makers' trademarks, used only to
    label the console, so they aren't shipped with Arcadia; it asks first and keeps the originals in
    `media/logos/source`). Each is then redrawn in its era's style: the NES logo a few chunky pixels in a handful of
    colours, the SNES's finer, the N64's sharper with more colours, the HD-era ones smooth, each on a light or dark
    plaque so black and white logos both show. A console with no logo shows its drawing: that's the arcade cabinet, as it has no single logo. All 33 consoles with a listed logo were
    downloaded and checked; the list is `arcadia/assets/logo_sources.json`.
  - **Console drawings**: original pixel-art drawings of each console (modelled in real centimetres with details
    placed from reference photographs, then drawn at its era's size and colour depth; `tools/make_console_art.py`,
    needs Pillow, numpy and PySide6; Arcadia itself only loads the finished PNGs).
  - **Your own pictures win over both**: View → "Use my own console pictures…" opens a folder where a PNG, WebP or
    JPEG named after the console (`nes.png`, `snes.png`, …) replaces what Arcadia would show, so you can drop in
    any logo or artwork you like.
- Sort by A–Z, recently played, most played, or favorites first (remembered between runs)
- Type a letter to jump to the next title starting with it; search with Ctrl+F
- Toast messages instead of dialogs, a live play timer on the Launch button, and a
  fullscreen mode for the couch (`python -m arcadia --fullscreen` or F11)
- Covers load lazily, so large libraries stay fast
- **Multi-disc games** become one library entry (an `.m3u` playlist), and **games with updates and
  DLC** (Nintendo Switch) show as one game with its update and DLC files attached
- **ROM sorting**: point Arcadia at your downloads folder and it moves each ROM into the
  right system folder, asking you whenever it isn't sure (see below)
- **Everything in one folder**: ROMs, emulators, BIOS files, covers, saves and the library live under one
  `Arcadia` folder, and Arcadia can install emulators into it (File → Emulators) so each one is self-contained
  instead of spread across Flatpak, `~/.config` and `~/.local/share`. `--home PATH` makes the whole thing portable
- **Update all** emulators in one step (File → Emulators… → Update all…), keeping the build you chose, with the
  Flatpak emulators optionally updated too and an optional check for updates when Arcadia starts
- A **Setup** window (File → Arcadia folder and setup…) that shows which systems are actually ready to play,
  brings an existing library into the Arcadia folder, and backs up and restores your saves and settings
- **34 systems** with launch presets (see the table below), from the NES to the PS3, Wii U and Xbox
- Presets for Nintendo (NES, SNES, Game Boy, Game Boy Color, GBA, N64, Switch), Sega (Genesis,
  Master System, Game Gear), and PlayStation / PSP, using standalone Flatpak emulators
  where they exist and RetroArch otherwise
- "Surprise me" picks a random game from the current system
- Its own app: Arcadia never adds games to your Steam library (deliberately; no Steam shortcuts).
- Controller-friendly: keyboard navigation works, and Steam Input maps a Steam Deck to it.
  A gamepad can also be read directly through evdev if the `evdev` package is installed.

## Getting started

The first time Arcadia runs it opens a short **Get started** checklist (also File → Get started…): your Arcadia
folder, adding your games, getting your emulators, BIOS files (optional), and syncing saves (optional). Each step
shows what Arcadia actually found (games in the library, emulators installed or ready through Flatpak, systems with
games that still lack a BIOS, whether rclone and your Drive remote exist) and has a button that opens the right
window; the checklist re-checks after each one. An empty shelf also says why it's empty and what to do (a new
library, an empty system, a search with no match, no favorites yet) instead of showing a blank screen.

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

Import ROMs normally looks only at the files directly in your downloads folder. To search deeper, use
**File → Import ROMs from a folder and its subfolders…** (Ctrl+Shift+I) and pick a folder; everything under it is
searched (game folders such as PS3 or Wii U count as one game). If a normal import finds nothing, it also offers
"Search subfolders too" and "Choose another folder…".

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

**What Arcadia does not do:** it can't make an emulator apply an update. Eden, Ryujinx and similar emulators
install updates and DLC through their own menus, and I haven't verified a command-line way to pass them,
so the Switch preset launches the base game only. If your emulator does take them on the command line,
use the placeholders in the launch command (Settings): `{rom}` the game, `{updates}` update files,
`{dlc}` DLC files, `{discs}` a multi-disc game's discs, e.g. `myemu --update {updates} --dlc {dlc} {rom}`.
`{stem}` is the file name without its extension and `{dir}` its folder (MAME wants both:
`-rompath {dir} {stem}`). A placeholder with nothing to fill it disappears, and every path is quoted.

Other limits: linking depends on the `[title ID]` in the file name, as in most dumps (the files' contents are
encrypted), so a file without one is treated as a game of its own. A DLC whose ID ends in `800` would be
mistaken for an update.

## Everything in one folder

A fresh install keeps everything under one folder, `~/Arcadia` by default:

```
Arcadia/
  roms/<system>/        your games, one folder per system (created for you)
  emulators/<name>/     one self-contained folder per installed emulator:
      app/                the program (an AppImage, or an unpacked archive)
      config/ data/       its settings, saves, shader caches and so on (see below)
      cache/ state/
      install.json        what was installed, from where, and whether its checksum was verified
  bios/                 a place for BIOS and firmware files
  media/                covers and metadata
  states/               save-state snapshots made by Arcadia
  data/                 the library database and the import undo journal
```

Change the folder in File → Settings → *Arcadia folder*. Any single location can still be set separately (say
ROMs on a big drive), and the rest stays inside the Arcadia folder. **An existing setup keeps working exactly as it
was** until you set an Arcadia folder; nothing is moved for you. If you do move, copy your ROMs into `roms/` yourself.

**Portable mode.** `python -m arcadia --home /path/to/Arcadia` (or the `ARCADIA_HOME` environment variable) runs
entirely from that folder, including its own `config.json`, and writes nothing to `~/.config` or `~/.local/share`.
Copy the folder to an SD card or another machine and point Arcadia at it.

### Installing emulators into that folder (File → Emulators…)

Eleven emulators can be installed here: PCSX2, RPCS3, Cemu, DuckStation, Flycast, melonDS, Azahar, RMG, mGBA, xemu
and Eden (for the Switch).
Pick one and Arcadia looks up the project's latest release **on your machine** and shows you exactly what it would
download (the file, its size, where it comes from, and whether a checksum will be checked) before anything is
fetched. Once installed, that system launches your copy; until then it uses the Flatpak, as before. You can switch
back at any time by clearing the *Installed emulator* column in Settings, or by removing the emulator.

**Updating.** *Update all…* looks up the latest release of every emulator installed here and shows what it would do
for each: the version change, the exact file, and whether that file's checksum can be checked. Then it installs the
ones you tick, one after another.
- **It keeps the build you chose.** Updating compares the new release's files with the one you installed, ignoring
  version numbers and commit hashes, so an Eden you picked the `steamdeck` build of stays the `steamdeck` build (not
  `amd64`, not `clang-pgo`). If it can't identify the same build with certainty (a project renamed its files, say), it
  doesn't guess: that row is left unticked with a menu of the new downloads for you to choose from.
- Each update uses the same installer as a first install: checksum verified when published, safe unpacking, and the
  old copy kept until the new one is in place. **One failure never stops the others**, and an emulator that fails to
  update still works as before. Your emulators' settings and saves are never touched.
- **Flatpak emulators** can be updated in the same step (a ticked option, shown with the list of apps). Arcadia asks
  Flatpak which are installed, leaves out any that a local copy has replaced, and runs
  `flatpak update -y --noninteractive` for **just those apps**, never everything on your machine. The command is the
  standard one but I couldn't run it against a real Flatpak install here, so treat its first use with the usual care.
  Cores you downloaded in RetroArch aren't updated by this; use RetroArch's own Online Updater.
- **Checking at startup is off by default.** Turn on *Check for emulator updates when Arcadia starts* in
  File → Settings and Arcadia will look in the background (it contacts GitHub, and Eden's own server) and show a
  message if updates are waiting. It never downloads anything by itself and never delays closing the app.

**Keeping each emulator's data in its own folder.** When Arcadia launches an installed emulator it sets
`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` to that emulator's folder, so its
settings, saves and shader caches land there and not in your home directory. This works for programs that follow
the XDG convention, which most Qt and SDL emulators do. **It is not guaranteed for every emulator**: one that
hard-codes its own location would ignore it, and one that wants BIOS files still needs pointing at the `bios/`
folder inside its own settings. Flatpak emulators are unaffected, because Flatpak keeps its own data under
`~/.var/app`.

**Safety.** Downloads only come over https from GitHub's own hosts, and a redirect to anywhere else is refused. The
file's SHA-256 is verified whenever GitHub publishes one (and the download is thrown away if it doesn't match);
when it doesn't, the dialog says the download can't be verified and the record notes it. Archives are unpacked
into a staging folder and can't write outside it (no `..` paths, absolute paths, or links). An update keeps the old
copy until the new one is in place, never touches the emulator's settings and saves, and a failed one leaves the
working copy alone. Removing offers to keep or delete the settings and saves. Nothing downloaded is run by the
installer.

**What I could and couldn't check.** I couldn't read any project's real release page from where this was built, so
the file-name patterns Arcadia uses to preselect a build are from my knowledge of each project and **unverified**.
That's why a wrong guess is harmless: the dialog lists every Linux 64-bit build it can unpack, preselects one only
if it matches, and otherwise asks you to choose. If nothing suitable is found it tells you and points to the
Flatpak. The installer itself was tested end to end against a local server, including attack cases, but not
against the real downloads.

**Not installable here:** Dolphin, PPSSPP, Snes9x, MAME, openMSX and FS-UAE publish no portable Linux build Arcadia
can install, RetroArch's is a `.7z`, and I couldn't confirm a download source for Ryujinx, so these stay on
Flatpak. AppImages need FUSE (SteamOS has it).

**Eden** is the one emulator here that isn't hosted on GitHub: its own server (`git.eden-emu.dev`) holds the
releases and a second host (`stable.eden-emu.dev`) serves the files, which is where Flathub's own metadata points
(GitHub only has its Flathub packaging). Arcadia asks that server directly, and **Eden may only be downloaded from
those two hosts**, nothing else, and no other emulator may use them. This one I checked against the live release
(v0.2.1): the list below was Eden's real file list and the download opens as a real AppImage.
- Eden publishes **no checksums**, so its installs are always marked "no checksum" and the confirmation says so.
- It publishes **eight Linux builds**: `amd64`, `legacy` (older CPUs), `rog-ally` and `steamdeck`, each as
  `gcc-standard` or `clang-pgo`. Arcadia preselects `amd64-gcc-standard`, but **on a Steam Deck choose the `steamdeck`
  build**; the confirmation lists all eight and says which suits which hardware.

When several downloads match a project's known pattern equally well, Arcadia no longer preselects any of them
and asks you to choose, since picking one would be arbitrary.

### Setup: what's ready, bringing your library in, and backups

File → **Arcadia folder and setup…** (Ctrl+Shift+S) is the one place to see and manage all of this.

**What's ready.** Each system that has games (or an emulator installed here) gets a row saying what it launches
with and whether that can work, and what to do if not. It only reports things it can really check:
- an emulator installed in the Arcadia folder is ready;
- a Flatpak command is checked with `flatpak info`, so "not installed" comes with the exact
  `flatpak install flathub …` line, and "Flatpak isn't available" is its own message;
- a RetroArch command also checks that the core file it names exists, and says to download it in RetroArch's
  Core Downloader if not;
- any other command is looked up on your path.

It does **not** check BIOS or firmware files: where an emulator wants them depends on its own settings, which Arcadia
can't see, so it won't claim they are found or missing. It also needs the `flatpak` program to answer for Flatpaks.
Space used by ROMs, emulators, save states, covers and backups is shown above the table.

**Bring my ROMs in.** (The button says "Bring my ROMs in…"; it covers your ROM folder and your Downloads folder.)
Point it at your existing ROM folder (the one holding `nes/`, `psx/`, `Game Boy Advance/`…).
It matches each subfolder to a system by name, including the names RetroPie, Batocera, EmuDeck and ES-DE use
(`megadrive`, `wswan`, `mame-libretro`, `ps1`…), shows the list with a system for each, and leaves unrecognised folders
(`Photos`) alone unless you choose a system for them. Then, after asking, it moves or copies what's inside into `roms/`.
- **Move** is fast on the same drive and is recorded, so File → Undo last import puts everything back. **Copy** keeps
  the old folder untouched but needs twice the space and can't be undone (delete the copies yourself).
- Nothing is ever overwritten: anything already in the destination is skipped and listed.
- Across drives a copy is checked (file count and size) before the original is removed.
- It refuses any folder that contains, or sits inside, the Arcadia ROM folder, so it can't move the Arcadia folder
  into itself.
- Optionally it also **copies** (never deletes) your library (favorites, play counts, playtime), covers and
  save-state snapshots, so the old setup keeps working until you're happy.
- Arcadia only switches over to the new folder if everything that could be brought in was. If something failed, it says
  what and why, keeps using the old folder, and you can run it again (what already moved is skipped). **Restart Arcadia**
  after it switches so the library opens from its new place.

**Sweeping your Downloads folder too.** Tick *Also sweep my Downloads folder for ROMs* and the same window also
looks through your downloads (the folder it offers comes from the system's `user-dirs.dirs` setting, so it's
`~/Downloads`, e.g. `/home/deck/Downloads` on a Steam Deck in Desktop Mode, unless you've changed it). You can use it with
a ROM folder, or on its own.
- **It looks inside subfolders**, two levels down, because ROMs are often unzipped into a folder. Hidden folders are
  skipped, a PS3 or Wii U game folder is taken whole rather than searched, and only things recognised as ROMs are ever
  listed. Everything else (photos, PDFs, installers) is counted and left alone.
- **It uses the same judgement as the downloads sorter**: header first, then the file's extension, then the name. What the
  evidence supports is ticked; anything uncertain is not. **Review the ROMs found in Downloads…** opens the same
  window as File → Import ROMs, so you can untick things or assign a system yourself, and it names the subfolder each ROM
  came from.
- **Where they go depends on what you're doing.** If a library is being moved in, the ROMs from Downloads go into the new
  Arcadia folder alongside it. If you only sweep Downloads, they go to the ROM folder you already use, so sweeping
  never quietly starts a second library.
- Nothing is overwritten (a ROM that already exists in the library is left in Downloads, and unticked), and the moves go
  in the undo journal, so File → Undo last import puts them back. With a library move too there are two steps to undo,
  one for each.
- **Keep watching this folder** is a separate box, off unless you tick it. It turns on the Settings option so *new*
  ROMs that land in Downloads are sorted automatically from then on. It never replaces a downloads folder you've already
  set there.

**Back up and restore.** One click makes a zip in `backups/` holding your Arcadia settings, the library (favorites and
playtime, copied consistently even while Arcadia is open), save-state snapshots, and each installed emulator's own
settings and saves (`config`, `data` and `state`, not its program or its cache). Covers are optional because they can be
large. It does **not** hold ROMs, emulator programs, or anything a Flatpak emulator keeps under `~/.var/app`.
- A restore only accepts those paths, so a backup file can put saves and settings back and nothing else: it can never
  place a program inside an emulator's `app/` folder, and paths like `../` are refused.
- It unpacks to a staging folder first, moves whatever it replaces to `backups/before-restore-<time>/` (nothing is
  deleted), and if it fails part way it puts everything back. A damaged zip is caught before anything changes.
- A backup restores onto another machine or folder by name, so it also moves your saves between setups.
- Restart Arcadia after restoring, so it loads the restored settings.

### BIOS, RetroArch settings, cores, Flatpak access and save sync (File → BIOS, emulator settings and sync…, Ctrl+Shift+B)

- **BIOS files.** Lists the BIOS / key files known systems want (PlayStation, PS2, Saturn, Sega CD, Dreamcast, GBA,
  DS, Lynx, PC Engine CD, Atari 7800, Switch `prod.keys`, Xbox) and whether a file with the right *name* is in
  `bios/` (up to two folders deep, any letter case). It doesn't supply files and can't tell a good dump from a bad
  one. The file names are the ones the emulators and libretro cores document; systems not listed aren't checked.
- **RetroArch settings.** When Arcadia starts RetroArch it adds `--appendconfig=<data>/retroarch-arcadia.cfg`, which
  RetroArch reads *on top of* your own `retroarch.cfg` (that file is never edited). It sets `system_directory` to
  `bios/` and, if you choose: fullscreen, vsync, integer scaling, auto save/load state, and keeping in-game saves in
  `saves/`. Existing saves aren't moved when you switch that last one on. Turn "Apply Arcadia's settings" off to stop
  all of it.
- **Cores.** Shows each core your RetroArch systems use and whether the file exists; one button installs the missing
  ones and refreshes the rest from libretro's nightly build server (`buildbot.libretro.com` only, one `.so` taken from
  the zip by exact name, checked to be a Linux program, swapped in atomically so a failed download leaves the old core).
- **Flatpak access.** Shows the exact `flatpak override --user --filesystem=<Arcadia folder> <app>` commands for the
  Flatpak emulators you use and runs them only after you confirm. (Undo: `flatpak override --user --reset <app>`.)
- **Save sync.** Pick a folder that Syncthing, a cloud drive or an SD card keeps in step; Arcadia makes that folder and
  your `saves/`, `states/` (and the RetroArch Flatpak's own saves) match. Nothing is deleted; a file changed on one
  side is copied across; changed on both, the newer wins and the other is kept in `_conflicts/`; anything overwritten
  here goes to `backups/savesync/` first. "Preview" shows what would happen.
  - **Google Drive** (or any cloud rclone supports): install [rclone](https://rclone.org/install/), run `rclone config`
    once and add a remote of type `drive` (it opens a browser to log in to Google; do this in Desktop Mode on a Deck),
    then `gdrive:Arcadia` is already filled in as the default (change it to match your remote's name) ("Find remotes" lists yours). Arcadia keeps a local mirror in
    `data/sync-cache`, pulls the Drive folder into it, runs the same sync as above, and pushes back, using only
    `rclone copy` (which never deletes). Arcadia never sees your Google login; rclone stores it. Use the same remote
    folder on every device. A plain folder is used only when the rclone box is empty.
  - **Automatic:** with a target set up and rclone installed, Arcadia syncs in the background when it starts and each
    time a game closes (never while one is running; launching waits if a sync is in progress). It shows a short message
    only when something was copied, conflicted or failed. Turn it off with the checkbox on the Save sync tab. It can't
    run while Arcadia is closed; it's tied to the app, not a background service.
- `saves/` is also part of backups now.

### Not done yet

What Arcadia still does **not** do:
- **Per-emulator settings for standalone emulators** (resolution, controller profiles). Each has its own settings file
  format, and I won't write files I haven't verified. Only RetroArch is configured (above).
- **Putting BIOS files where each standalone emulator looks.** RetroArch is pointed at `bios/`; for the others, copy
  the files into that emulator's own BIOS folder.
- **Syncing the data of emulators installed in Arcadia's folder** (`emulators/<id>/data`), which can be huge; use the
  backup for those.
- Installing emulators that only ship as a Flatpak or as a `.7z`.

**Not verified on real hardware:** that a Flatpak RetroArch accepts the `--appendconfig` file (it needs the folder
access above), real rclone and Google Drive (the tests use a stand-in for rclone and I couldn't run rclone here, so the `listremotes --long` output format is from its documentation), the libretro build server's file layout beyond what was read from its listing, and every sync/override
command beyond the automated tests, which use stand-ins for Flatpak and the network.

## Supported systems

Every system below is in the default setup with a launch preset. Systems with no games are hidden from the
bar, so only the ones you use show up. Folder names are under your ROM root.

| System | Folder | Emulator (Flatpak ID, or RetroArch core) |
|---|---|---|
| NES | `nes` | RetroArch `nestopia` |
| Super Nintendo | `snes` | Snes9x `com.snes9x.Snes9x` |
| Nintendo 64 | `n64` | RMG `com.github.Rosalie241.RMG` |
| GameCube / Wii | `gamecube` / `wii` | Dolphin `org.DolphinEmu.dolphin-emu` |
| Wii U | `wiiu` | Cemu `info.cemu.Cemu` |
| Switch | `switch` | Eden `dev.eden_emu.eden` |
| Game Boy / Color / Advance | `gb` / `gbc` / `gba` | mGBA `io.mgba.mGBA` |
| Nintendo DS | `nds` | melonDS `net.kuribo64.melonDS` |
| Nintendo 3DS | `3ds` | Azahar `org.azahar_emu.Azahar` |
| Genesis, Master System, Game Gear, Sega CD | `genesis`, `mastersystem`, `gamegear`, `segacd` | RetroArch `genesis_plus_gx` |
| Sega Saturn | `saturn` | RetroArch `mednafen_saturn` |
| Dreamcast | `dreamcast` | Flycast `org.flycast.Flycast` |
| PlayStation | `psx` | DuckStation `org.duckstation.DuckStation` |
| PlayStation 2 | `ps2` | PCSX2 `net.pcsx2.PCSX2` |
| PlayStation 3 | `ps3` | RPCS3 `net.rpcs3.RPCS3` |
| PSP | `psp` | PPSSPP `org.ppsspp.PPSSPP` |
| Xbox | `xbox` | xemu `app.xemu.xemu` |
| PC Engine, Neo Geo | `pcengine`, `neogeo` | RetroArch `mednafen_pce_fast`, `fbneo` |
| Arcade | `arcade` | MAME `org.mamedev.MAME` |
| Atari 2600 / 7800 / Lynx | `atari2600`, `atari7800`, `lynx` | RetroArch `stella`, `prosystem`, `handy` |
| WonderSwan, Neo Geo Pocket, Virtual Boy | `wonderswan`, `ngp`, `virtualboy` | RetroArch `mednafen_wswan`, `mednafen_ngp`, `mednafen_vb` |
| MSX | `msx` | openMSX `org.openmsx.openMSX` |
| Amiga | `amiga` | FS-UAE `net.fsuae.FS-UAE` |

**What was checked.** Every Flatpak ID exists on Flathub and every RetroArch core file exists on the libretro
build server. The command-line options were read from each project's own source for Dolphin (`-b -e`), PCSX2
(`-batch --`), Cemu (`-g`), Eden (`-g`), RPCS3 (a path argument), melonDS (a ROM argument), xemu (`-dvd_path`),
RMG and MAME (`-rompath`). **They were not confirmed** for Azahar, Flycast, FS-UAE, openMSX, DuckStation, PPSSPP,
mGBA or Snes9x: those use the usual "emulator file" form, but run each once and fix the command in Settings if it
isn't right. Save folders are only preset for RetroArch.

**What each needs from you.** Arcadia launches emulators; it doesn't set them up.
- RetroArch cores are downloaded on demand (Online Updater → Core Downloader), once each.
- BIOS or firmware files are needed for PS1, PS2, Saturn, Sega CD, Dreamcast, Neo Geo, MSX, Amiga, Xbox
  (xemu wants a BIOS and a hard-disk image), and for Switch the prod keys.
- MAME and FinalBurn Neo want exact ROM sets: the zip's name is the game, so don't rename them.
- RPCS3 can't boot an encrypted PS3 `.iso`; use a decrypted dump or a game folder.
- Wii U updates and DLC, like Switch ones, are installed from inside Cemu, not by Arcadia.

**Not added, and why.** PS4 (shadPS4 is early-stage and I couldn't verify how to launch a dump), PS Vita (Vita3K
isn't on Flathub), ScummVM and DOSBox (they launch a game *folder* with per-game setup, which doesn't fit "one
launch command per system"), Mednafen and ares (RetroArch covers those systems), and Xbox 360 or Windows games.

## Game folders (PS3, Wii U)

Some games are a folder, not a file. For PS3 and Wii U, a folder counts as one game when it holds the right
marker file, and that file is what gets launched:

| System | Folder is a game when it contains | Launches | Title read from |
|---|---|---|---|
| PS3 | `PS3_GAME/USRDIR/EBOOT.BIN` (or `USRDIR/EBOOT.BIN`) | that `EBOOT.BIN` | `PARAM.SFO` |
| Wii U | `code/*.rpx` | that `.rpx` | `meta/meta.xml` |

The folder name (`BLUS30443`) is the fallback title. Nothing inside a game folder shows up as a separate game.
From the downloads folder, a game folder is recognised the same way and moved as a unit. Moving a folder across
drives copies it, checks the file count and total size, and only then removes the original.

## How disc images are told apart

PlayStation 1 and 2 discs both carry a "PLAYSTATION" marker, so Arcadia reads the disc's own file system
instead: `SYSTEM.CNF` says `BOOT` on a PS1 disc and `BOOT2` on a PS2 disc. It also reads the PSP, PS3, Xbox,
GameCube, Wii, Saturn, Sega CD and Dreamcast layouts, looks inside compressed PSP `.cso` files, and reads the
kind of disc (CD, DVD, GD-ROM) from a `.chd`. A `.cue` or `.gdi` sheet is judged by its data track.

When the contents can't settle it, Arcadia asks rather than guessing: a disc image it can't place defaults to
the likeliest system but stays unticked. Playlists for multi-disc games are only made for PlayStation, Saturn
and Sega CD, because those are the emulators that open them.

Limits: all of this was tested against disc and ROM images I built from the published formats, not against
real dumps, so an unusual real file may land in "unsure". That is the safe direction.

## Presets and Flatpak access (the fallback)

Launch commands default to the presets in `arcadia/presets.py`. The Switch now defaults to Eden
(`dev.eden_emu.eden`). Ryujinx from the Ryubing fork (`io.github.ryubing.Ryujinx`) also has a Flathub build: to use it, set
the Switch launch command to `flatpak run io.github.ryubing.Ryujinx {rom}` in Settings and clear its *Installed
emulator*. An existing setup that already uses Ryujinx is left as it is. Their Flatpak IDs were
checked on Flathub. The command-line options and save folders are the usual defaults and
should be checked on your machine. Settings → "Reset launch commands to presets" restores them.

Flatpak apps can only read folders they've been granted, so grant your ROM folder once per app:

```bash
# run once per emulator you use
for app in org.libretro.RetroArch io.mgba.mGBA com.snes9x.Snes9x org.duckstation.DuckStation org.ppsspp.PPSSPP dev.eden_emu.eden org.DolphinEmu.dolphin-emu info.cemu.Cemu net.kuribo64.melonDS org.azahar_emu.Azahar net.pcsx2.PCSX2 net.rpcs3.RPCS3 app.xemu.xemu org.flycast.Flycast com.github.Rosalie241.RMG org.mamedev.MAME org.openmsx.openMSX net.fsuae.FS-UAE; do
  flatpak override --user --filesystem=/path/to/ROMs "$app"
done
```

Save-state snapshots only work where the save folder is set. Standalone presets
(mGBA, Snes9x, DuckStation, PPSSPP) have no save folder set by default, because the
exact location depends on the emulator's configuration. Set it in Settings if you want snapshots.

Folder choosers inside Arcadia (Arcadia folder, ROM folder, downloads folder, sync folder) are
controller-friendly: a "Jump to…" list (Home, Downloads, plugged-in memory cards and USB drives), then A on a
folder opens it. View > Check my console pictures tells you what's wrong with pictures in `media/consoles`. Installing
an emulator shows speed and time left and has a Cancel button.

## Updating Arcadia

File > Check for Arcadia updates… asks GitHub whether the branch you follow has newer commits, lists what changed,
and updates when you say so, then offers to restart. A copy installed with `git clone` is fast-forwarded with git
(it refuses if you've edited files); a copy without git is replaced from GitHub's zip, with the old files kept in
`.previous`. Your games, saves and settings live in your Arcadia folder and are never touched. Turn on
"Check for a newer Arcadia when it starts" in Settings for a quiet note at startup. The repository must be public
for this to work. If an update changes `requirements.txt`, run `./install.sh` once afterwards.

## Install and run on a Steam Deck (or any Linux PC)

In Desktop Mode, open a terminal in the Arcadia folder and run:

```bash
./install.sh        # private Python environment + an "Arcadia" entry in the application menu
./arcadia.sh        # start it full screen   (./arcadia.sh --windowed for a normal window)
./install.sh --uninstall   # remove the environment and menu entry (never your ROMs or saves)
```

Arcadia is its own app: nothing is added to Steam and your games never appear in the Steam library. To start it
from Game Mode, add `arcadia.sh` yourself (Steam > Add a Non-Steam Game > browse to it). The launcher then asks
Qt for gamescope's X11 display automatically. A Steam Input layout with the gamepad template works for the
controls. Not yet tried on real Deck hardware.

In Steam's controller settings for Arcadia, bind: D-pad to the arrow keys, **A** to Enter, **B** to Escape,
**Y** to Ctrl+D, left/right bumper to Page Up / Page Down, and the left stick to the arrow keys too. That covers
every control in the table below. `docs/steam-input.md` has the same list to follow button by button.

## Install (development)

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

| Action | Keyboard | Controller (evdev / Steam Input) |
|--------|----------|----------------------------------|
| Rotate the consoles (console screen) | Left / Right (Up / Down too), mouse wheel, or click one | D-pad |
| Open the middle console | Enter / click it | A |
| Browse games (game screen) | Left / Right | D-pad left / right |
| Launch the game | Enter | A |
| Back to the consoles | Esc / Backspace | B |
| Jump to a console or a game | Type a letter | — |
| Change console without going back (game screen) | Page Up / Page Down | Left / right bumper |
| Favorite | Ctrl+D | Y (game screen) |
| Search (all games, from the console screen) | Ctrl+F | — |
| Fullscreen | F11 | — |
| Rescan | Ctrl+R | — |

**In dialogs** (Settings, Setup, Emulators, the checklist and so on) the controller drives the dialog instead of the
window behind it: the D-pad steps through the controls (or moves within a list, table or drop-down), A presses the
focused control, B closes the dialog (or just an open drop-down), and the bumpers change tab. The focused control is
outlined in the accent colour. Every dialog fits a Steam Deck's screen and shrinks to any smaller one.

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
  discs.py       disc image analysis: ISO 9660, PS1 vs PS2, Nintendo/Sega/Xbox discs, CSO, CHD
  folders.py     games that are folders (PS3, Wii U) and their titles
  emulators.py   install emulators into their own folders: catalog, safe download, unpack, isolation
  emulators_dialog.py  the Emulators window, including Update all
  updates.py     plan and apply updates for every emulator, keeping the installed build; Flatpak updates
  setup_status.py  is each system ready to play? (Flatpak, core file, command checks, folder sizes)
  consolidate.py bring an existing library into the Arcadia folder
  backup.py      back up and restore saves, settings and the library
  setup_dialog.py  the Setup window, bring-in and backup dialogs
  tasks.py       background work so windows never freeze
  files_dialog.py  every file that makes up a game
  import_dialog.py  the confirm-before-moving dialog
  library.py     SQLite store (games, favorites, sessions)
  launcher.py    launch template -> argument list
  savestates.py  snapshot / restore of per-game saves
  metadata.py    sidecar JSON and cover art
  presets.py     launch presets and system accent colors
  theme.py       stylesheet, animated backdrop, toast messages
  coverflow.py   animated cover-flow carousel with lazy cover loading
  consoles_view.py  the rotating console carousel (the first screen)
  pixelart.py    picks each console's picture (yours, the bundled pixel art, or a generic cartridge) and draws the glow
  eras.py        which bit-generation each console belongs to (8-bit ... HD), and each era's pixel size and colour depth
  logos.py       downloads console logos to your media folder and redraws them in each console's era style
  transitions.py the zoom between the two screens
  sounds.py      the small sound effects (assets/sounds/*.wav)
  assets/consoles/  the bundled pixel-art console pictures and their credits
  ../tools/      scripts that rebuild those pictures from the source photographs
  gamepad.py     optional evdev controller input
  ui.py          Qt windows and dialogs
  main.py        entry point
tests/
  test_core.py   scanning, library, launching, save states, config
  test_sorter.py ROM identification, plans, safe moves, and undo
  test_bundles.py  disc-name, playlist, and title-ID parsing
  test_multifile.py  multi-disc sets and update/DLC bundles end to end
  test_discs.py  disc image analysis
  test_emulators.py  the installer, against a real local server (including attack cases)
  test_updates.py    updating everything: same-build matching, failure isolation, Flatpak
  test_home.py   the single-folder layout and portable mode
  test_setup_status.py  readiness checks
  test_consolidate.py   bringing a library in
  test_backup.py        backup and restore, including hostile archives
  test_setup_dialog.py  the Setup, bring-in and backup windows
  test_sweep.py         finding the downloads folder, and sweeping it and its subfolders
  test_newsystems.py  the extra systems, folder games, presets, and disc disambiguation
  isoutil.py     builds valid disc images for the tests
  test_ui.py     window, cover flow, and import dialog tests (skipped where Qt can't load)
```
