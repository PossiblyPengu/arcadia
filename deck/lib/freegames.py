#!/usr/bin/env python3
"""Free games: homebrew and freeware Arcadia can download and add for you.

Two sources, both free to share:

* Homebrew Hub (hh.gbdev.io): the Game Boy, Game Boy Color, Game Boy Advance and NES homebrew collection. Only
  entries marked as games are offered (not demos, tools or music), never one marked commercial.
* libretro's freeware library (buildbot.libretro.com/assets/cores), the one RetroArch's Content Downloader uses:
  homebrew and freeware sorted by console, and the Doom shareware episode. Test ROMs are left out.

    freegames.py list             one line per game, for Arcadia's Free games screen (see `list_lines`)
    freegames.py about ID         the game's name, who made it and what it is, for its details
    freegames.py install ID       download it into the right ROM folder, with its name, description and picture

The list is kept for a day (`~/Arcadia/deck/free-games.json`) and used as it is when the sources can't be reached.
Downloads come only from those two hosts, over HTTPS. Neither publishes checksums for these files, so they are
checked by size and kind (a ROM, or a zip that opens) only.
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emulators  # noqa: E402  (Arcadia's console list, for folders and names)

HOME = Path.home()
ESDE = Path(os.environ.get("ARCADIA_HOME", HOME / "Arcadia"))
HH = os.environ.get("FREEGAMES_HH_URL", "https://hh3.gbdev.io")
LR = os.environ.get("FREEGAMES_LR_URL", "https://buildbot.libretro.com/assets/cores")
HOSTS = {"hh3.gbdev.io", "buildbot.libretro.com"}
TEST_MODE = "FREEGAMES_HH_URL" in os.environ or "FREEGAMES_LR_URL" in os.environ  # tests serve from 127.0.0.1
CACHE = ESDE / "deck" / "free-games.json"
FRESH = 24 * 3600
CACHE_FORMAT = 2  # (bumped when what the cache holds changes)
MAX_BYTES = 64 << 20
RETROARCH_SYSTEM = Path(os.environ.get("ARCADIA_RETROARCH_SYSTEM",
                                       HOME / ".var/app/org.libretro.RetroArch/config/retroarch/system"))

# Homebrew Hub's platforms → Arcadia's consoles.
HH_SYSTEMS = {"GB": "gb", "GBC": "gbc", "GBA": "gba", "NES": "nes"}
# libretro's folders → Arcadia's consoles (only consoles whose games can stay zipped, and Doom).
LR_SYSTEMS = {
    "Nintendo - GameBoy": "gb", "Nintendo - GameBoy Advance": "gba", "Nintendo - Nintendo Entertainment System": "nes",
    "Nintendo - Super Nintendo Entertainment System": "snes", "Nintendo - Nintendo 64": "n64",
    "Nintendo - Virtual Boy": "virtualboy", "Nintendo - Pokemon Mini": "pokemini",
    "Sega - Mega Drive - Genesis": "genesis", "Sega - Master System - Mark III": "mastersystem",
    "Sega - Game Gear": "gamegear", "NEC - PC Engine - TurboGrafx 16": "pcengine", "Atari - 2600": "atari2600",
    "GCE - Vectrex": "vectrex", "Mattel - Intellivision": "intellivision", "Coleco - Colecovision": "colecovision",
    "Bandai - WonderSwan Color": "wonderswancolor", "Arduous": "arduboy", "WASM-4": "wasm4", "DOOM": "doom",
}
# A console another name also uses: install into the folder that already exists.
ALIASES = {"genesis": "megadrive", "megadrive": "genesis"}
NOT_GAMES = re.compile(r"240p|test ?suite|testrom|\btest\b", re.I)
REGION = re.compile(r"\s*\((?:USA|Europe|Japan|World|En|Fr|De|Es|It|Ja|[A-Z][a-z]?(?:,[A-Z][a-z]?)*)\)", re.I)


class FreeGamesError(Exception):
    pass


@dataclass
class Game:
    id: str  # "hh:<slug>" or "lr:<folder>/<file>"
    system: str  # Arcadia's console name, e.g. "gb"
    title: str
    by: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""  # the file to download
    filename: str = ""  # what it is called in the ROM folder
    pictures: list[str] = field(default_factory=list)  # screenshot URLs, the title screen first
    licence: str = ""
    page: str = ""  # where to read more (the developer's or the project's page)


# ---- fetching -------------------------------------------------------------------------------------------------------

def _open(url: str):
    p = urlparse(url)
    local = TEST_MODE and p.hostname in ("127.0.0.1", "localhost")
    if not local and (p.scheme != "https" or p.hostname not in HOSTS):
        raise FreeGamesError(f"refusing to download from {url}")
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "arcadia-free-games"}),
                                      timeout=60)
    except OSError as exc:
        raise FreeGamesError(f"couldn't reach {p.hostname} ({getattr(exc, 'reason', exc)})") from exc


def fetch(url: str, limit: int = MAX_BYTES) -> bytes:
    with _open(url) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise FreeGamesError(f"{url.rsplit('/', 1)[-1]} is bigger than expected")
    return data


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def _name(text: str) -> str:
    """A game's name as a list shows it: plain text, and not shouted (SUPER GAME → Super Game; short words such as GBA
    or EX stay as they are)."""
    name = _plain(text)
    if name.isupper():
        name = re.sub(r"[A-Z]{4,}", lambda m: m.group().capitalize(), name)
    return name


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _sort_key(title: str) -> str:
    return re.sub(r"^[^0-9a-z]+", "", title.lower()) or title.lower()


def homebrew_hub(get=fetch) -> list[Game]:
    data = json.loads(get(f"{HH}/api/search?page=1&results=5000", 32 << 20))
    games = []
    for e in data.get("entries", []):
        if e.get("typetag") != "game" or e.get("commercial"):
            continue
        system = HH_SYSTEMS.get(e.get("platform") or ("GB" if e.get("basepath") == "database-gb" else ""))
        files = [f for f in e.get("files", []) if f.get("playable")]
        if not system or not files or not e.get("slug") or not e.get("basepath"):
            continue
        rom = next((f for f in files if f.get("default")), files[0])["filename"]
        base = f"{HH}/static/{quote(e['basepath'])}/entries/{quote(e['slug'])}/"
        shots = sorted(e.get("screenshots") or [], key=lambda s: (not s.lower().startswith("title"), s))
        names, page = _people(e.get("developer"))
        site = e.get("website") or e.get("repository") or page
        page = site[0] if isinstance(site, list) and site else site if isinstance(site, str) else page
        games.append(Game(f"hh:{e['slug']}", system, _name(e.get("title") or "") or _capital(_title(rom)),
                          ", ".join(names), _plain(e.get("description") or ""), list(e.get("tags") or []),
                          base + quote(rom), Path(rom).name, [base + quote(s) for s in shots[:2]],
                          str(e.get("license") or ""), str(page or "")))
    return games


def _people(dev) -> tuple[list[str], str]:
    """Who made it (names), and a link to them if there is one. The database has a name, a {name, link}, or a list."""
    items = dev if isinstance(dev, list) else [dev]
    names, link = [], ""
    for d in items:
        if isinstance(d, dict):
            if d.get("name"):
                names.append(str(d["name"]))
            link = link or str(d.get("link") or "")
        elif d:
            names.append(str(d))
    return names, link


def _title(filename: str) -> str:
    name = unquote(filename)
    for ext in (".zip", ".7z"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
    name = re.sub(r"\.[A-Za-z0-9]{1,4}$", "", name)
    name = REGION.sub("", name).replace("_", " ").strip()
    return name or unquote(filename)


def _listing(url: str, get=fetch) -> list[str]:
    """The files (not folders) a web directory listing links to."""
    page = get(url, 4 << 20).decode("utf-8", "replace")
    out = []
    for href in re.findall(r'href="([^"]+)"', page):
        full = urljoin(url, html.unescape(href))
        if full.startswith(url) and full != url and not full.endswith("/") and "?" not in full:
            name = full[len(url):]
            if "/" not in name and name not in out:
                out.append(name)
    return out


def libretro(get=fetch, before: list[Game] | None = None) -> list[Game]:
    """libretro's freeware, folder by folder. A folder that can't be read keeps its games from before (if any)."""
    games = []
    for folder, system in LR_SYSTEMS.items():
        url = f"{LR}/{quote(folder)}/"
        try:
            names = _listing(url, get)
        except FreeGamesError:
            games += [g for g in before or [] if g.id.startswith(f"lr:{folder}/")]
            continue
        if folder == "DOOM":  # the shareware episode, and the data file PrBoom needs (installed with it)
            names = [n for n in names if unquote(n).lower().endswith(".zip")]
        for name in names:
            plain = unquote(name)
            if NOT_GAMES.search(plain) or plain.lower().endswith((".txt", ".md", ".png", ".jpg")):
                continue
            games.append(Game(f"lr:{folder}/{plain}", system, _title(name), "", "", [], url + name, plain, [], "", ""))
    return games


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def catalogue(refresh: bool = False, get=fetch) -> list[Game]:
    """Every free game, from the cache if it's fresh (or the sources can't be reached)."""
    cached = None
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached.get("format") != CACHE_FORMAT:
            cached = None  # (written by an older version: fetched again)
    except (OSError, ValueError, AttributeError):
        pass
    if cached and not refresh and time.time() - float(cached.get("at", 0)) < FRESH:
        return [Game(**g) for g in cached["games"]]
    try:
        hh = homebrew_hub(get)
    except (FreeGamesError, ValueError) as exc:
        if cached:
            return [Game(**g) for g in cached["games"]]
        raise FreeGamesError(f"the list of free games couldn't be fetched: {exc}") from exc
    lr_all = libretro(get, [Game(**g) for g in (cached or {}).get("games", []) if g["id"].startswith("lr:")])
    seen = {(g.system, _key(g.title)) for g in hh}
    lr = [g for g in lr_all if (g.system, _key(g.title)) not in seen]  # (Homebrew Hub's has the details)
    games = hh + lr
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"format": CACHE_FORMAT, "at": time.time(), "games": [asdict(g) for g in games]}),
                   encoding="utf-8")
    os.replace(tmp, CACHE)
    return games


# ---- where things go ------------------------------------------------------------------------------------------------

def roms() -> Path:
    return Path(os.environ.get("ARCADIA_ROMS") or HOME / "ROMs")


def consoles() -> dict[str, emulators.System]:
    """Arcadia's consoles by name."""
    return {s.name: s for s in emulators.load_systems(emulators.systems_files()).values()}


def place(system: str, known: dict[str, emulators.System]) -> tuple[Path, str]:
    """The console's ROM folder, and the console that owns it (whose game list and pictures it uses). A folder that
    already exists under the console's other name wins (megadrive / genesis), so a collection isn't split."""
    def folder(name: str) -> Path:
        return roms() / (known[name].folder if name in known else name)

    other = ALIASES.get(system)
    if other and not folder(system).is_dir() and folder(other).is_dir():
        return folder(other), other
    return folder(system), system


def installed_path(g: Game, known: dict[str, emulators.System]) -> Path:
    folder = place(g.system, known)[0]
    if g.system == "doom" and g.filename.lower().endswith(".zip"):
        return folder / (Path(g.filename).stem + ".wad")
    return folder / g.filename


def is_installed(g: Game, known: dict[str, emulators.System]) -> bool:
    return installed_path(g, known).exists()


# ---- what the screen shows ------------------------------------------------------------------------------------------

def _short(text: str, n: int) -> str:
    text = text.replace("|", "/").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


def list_lines(games: list[Game]) -> list[str]:
    """game|id|console|console name|title|by|installed|blurb, by console (most games first) then title."""
    known = consoles()
    counts: dict[str, int] = {}
    for g in games:
        if g.system in known:
            counts[g.system] = counts.get(g.system, 0) + 1

    def field(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("|", "/")).strip()

    out = []
    shown = sorted((g for g in games if g.system in known),
                   key=lambda g: (-counts[g.system], g.system, _sort_key(g.title)))
    for g in shown:
        blurb = _short(g.description, 110) if g.description else ", ".join(g.tags[:3])
        out.append("|".join(("game", field(g.id), g.system, field(known[g.system].fullname), field(_short(g.title, 60)),
                             field(_short(g.by, 40)), "1" if is_installed(g, known) else "0", field(blurb))))
    return out


def about(g: Game) -> str:
    known = consoles()
    lines = [g.title]
    who = f"by {g.by}" if g.by else "freeware from libretro's library"
    lines.append(f"{known[g.system].fullname if g.system in known else g.system} · {who}")
    if g.description:
        lines += ["", _short(g.description, 520)]
    if g.licence:
        lines += ["", f"Licence: {g.licence}"]
    if g.page:
        lines.append(f"More: {g.page}")
    return "\n".join(lines)


# ---- installing -----------------------------------------------------------------------------------------------------

def say(text: str) -> None:
    print(text, flush=True)


def _looks_like_rom(data: bytes, name: str) -> bool:
    if len(data) < 32:
        return False
    if name.lower().endswith(".zip"):
        return data[:2] == b"PK"
    return not data[:64].lstrip().lower().startswith((b"<!doctype", b"<html"))  # (not an error page)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _add_to_gamelist(g: Game, rom: Path, owner: str) -> None:
    """Name, description, developer and genre in Arcadia's game list, so the game looks finished straight away."""
    path = ESDE / "gamelists" / owner / "gamelist.xml"
    try:
        root = ET.parse(path).getroot() if path.is_file() else ET.Element("gameList")
    except ET.ParseError:
        return  # someone else's broken file: leave it alone
    entry = f"./{rom.name}"
    if any((game.findtext("path") or "") == entry for game in root.iter("game")):
        return
    game = ET.SubElement(root, "game")
    for tag, value in (("path", entry), ("name", g.title), ("desc", g.description), ("developer", g.by),
                       ("genre", ", ".join(g.tags[:3]))):
        if value:
            ET.SubElement(game, tag).text = value
    ET.indent(root)
    tmp = path.with_name("gamelist.xml.part")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text('<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    os.replace(tmp, path)


def install(game_id: str, get=fetch) -> int:
    games = {g.id: g for g in catalogue(get=get)}
    g = games.get(game_id)
    if g is None:
        say("✗ That game isn't in the list any more.")
        return 1
    known = consoles()
    target = installed_path(g, known)
    if target.exists():
        say(f"✓ {g.title} is already in your {known[g.system].fullname if g.system in known else g.system} games.")
        return 0
    console = known[g.system].fullname if g.system in known else g.system
    say(f"Getting {g.title} for {console}…")
    print("@progress 0/2", flush=True)
    data = get(g.url)
    if not _looks_like_rom(data, g.filename):
        say("✗ What came back isn't a game file, so nothing was added.")
        return 1
    if g.system == "doom" and g.filename.lower().endswith(".zip"):
        try:  # the episode's .wad goes in the Doom folder, PrBoom's own data file where RetroArch looks for it
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                wads = [n for n in z.namelist() if n.lower().endswith(".wad")]
                if not wads:
                    raise FreeGamesError("The Doom download has no .wad file in it, so nothing was added.")
                _write(target, z.read(wads[0]))
            prboom = RETROARCH_SYSTEM / "prboom.wad"
            if not prboom.exists():
                _write(prboom, get(f"{LR}/DOOM/prboom.wad", 8 << 20))
        except (zipfile.BadZipFile, FreeGamesError) as exc:
            say(f"✗ {exc}")
            return 1
    else:
        if g.filename.lower().endswith(".zip"):
            try:
                zipfile.ZipFile(io.BytesIO(data)).testzip()
            except zipfile.BadZipFile:
                say("✗ The download is damaged, so nothing was added.")
                return 1
        _write(target, data)
    say(f"  ✓ {g.title} is in your {console} games ({target.parent})")
    print("@progress 1/2", flush=True)
    owner = place(g.system, known)[1]
    for url in g.pictures[:1]:  # its title screen as the cover Arcadia's cards show, and as a screenshot
        try:
            ext = Path(urlparse(url).path).suffix.lower() or ".png"
            picture = get(url, 8 << 20)
            for kind in ("covers", "screenshots"):
                _write(ESDE / "downloaded_media" / owner / kind / (target.stem + ext), picture)
            say("  ✓ Its title screen, as its cover and screenshot")
        except (FreeGamesError, OSError):
            say("  ○ No picture this time: Covers and info can get one later.")
    _add_to_gamelist(g, target, owner)
    print("@progress 2/2", flush=True)
    if g.page:
        say(f"  → Made by {g.by}: {g.page}" if g.by else f"  → More about it: {g.page}")
    say("")
    say(f"{g.title} is ready. It shows under {console} when you leave Free games.")
    return 0


def main(argv: list[str]) -> int:
    cmd, args = (argv[0] if argv else "list"), argv[1:]
    try:
        if cmd == "list":
            print("\n".join(list_lines(catalogue(refresh="--refresh" in args))))
            return 0
        if cmd == "about" and args:
            g = {g.id: g for g in catalogue()}.get(args[0])
            print(about(g) if g else "That game isn't in the list any more.")
            return 0 if g else 1
        if cmd == "install" and args:
            return install(args[0])
    except FreeGamesError as exc:
        text = _capital(str(exc))
        say(f"✗ {text}" + ("" if text.endswith(".") else "."))
        if cmd == "install":
            say("")
            say("Nothing was added. Check the Deck is online, then try again (or pick another game).")
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
