"""Console logos: downloaded to the user's folder, redrawn per era, and switchable with the drawings."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcadia import eras, logos, pixelart  # noqa: E402
from arcadia.emulators import EmulatorError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def make_logo(path=None, dark=True, size=(300, 110)):
    """A stand-in logo: a transparent picture with a bar and a stripe in it."""
    image = QImage(*size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#101018" if dark else "#f4f4f8"))
    painter.drawRect(20, 25, size[0] - 40, size[1] - 50)
    painter.setBrush(QColor("#d6322c"))
    painter.drawRect(40, 45, size[0] - 80, 18)
    painter.end()
    if path is not None:
        image.save(str(path))
    return image


def colours(image):
    return {image.pixelColor(x, y).rgb() for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0}


def test_a_logo_is_redrawn_in_each_eras_size_and_colour_depth(qapp):
    source = make_logo()
    widths = []
    for label in eras.LABELS:
        style = eras.STYLES[label]
        out = logos.pixelate_logo(source, style)
        widths.append(out.width())
        assert out.width() <= style.width + 2 and out.height() >= 8, label
        assert len(colours(out)) <= style.colors + 2, label  # the palette, plus the outline and the plaque edge
        assert out.pixelColor(0, 0).alpha() == 0  # the corner of the plaque is rounded away
    assert widths == sorted(widths) and widths[-1] > widths[0] * 2  # later eras are bigger and finer


def test_early_eras_have_hard_pixels_and_late_ones_soft_edges(qapp):
    source = make_logo()
    hard = logos.pixelate_logo(source, eras.STYLES["8-bit"])
    soft = logos.pixelate_logo(source, eras.STYLES["HD"])
    partial = lambda img: sum(0 < img.pixelColor(x, y).alpha() < 255 for x in range(img.width()) for y in range(img.height()))  # noqa: E731
    assert partial(hard) == 0 and partial(soft) > 0


def test_dark_logos_get_a_light_plaque_and_light_logos_a_dark_one(qapp):
    style = eras.STYLES["32-bit"]
    on_dark = logos.pixelate_logo(make_logo(dark=True), style)
    on_light = logos.pixelate_logo(make_logo(dark=False), style)
    corner = lambda img: img.pixelColor(4, img.height() // 2)  # noqa: E731
    assert corner(on_dark).lightness() > 180 and corner(on_light).lightness() < 90


def test_an_empty_picture_is_refused(qapp):
    empty = QImage(50, 50, QImage.Format.Format_ARGB32)
    empty.fill(0)
    with pytest.raises(EmulatorError):
        logos.pixelate_logo(empty, eras.STYLES["16-bit"])


class FakeFetcher:
    """Serves local pictures instead of the network; some names fail."""

    def __init__(self, picture, missing=()):
        self.picture, self.missing, self.asked = picture, set(missing), []

    def download(self, url, dest, progress=None):
        self.asked.append(url)
        if any(name in url for name in self.missing):
            raise EmulatorError("that release or file wasn't found")
        if "notapicture" in url:
            dest.write_bytes(b"<html>nope</html>")
        else:
            self.picture.save(str(dest))
        return "x"


def with_sources(monkeypatch, tmp_path, data):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(logos, "SOURCES", path)


def test_fetch_saves_the_original_and_the_pixel_logo_and_tries_other_names(qapp, tmp_path, monkeypatch):
    with_sources(monkeypatch, tmp_path, {"nes": ["Gone.svg", "NES_logo.svg"], "snes": ["Super.png"], "n64": ["Missing.svg"]})
    media = tmp_path / "media"
    fetcher = FakeFetcher(make_logo(), missing=("Gone.svg", "Missing.svg"))
    seen = []
    result = logos.fetch_logos(media, fetcher=fetcher, progress=lambda d, t: seen.append((d, t)), pause=0)
    assert sorted(result.done) == ["nes", "snes"] and list(result.failed) == ["n64"]
    for cid in ("nes", "snes"):
        assert (media / "logos" / "source" / f"{cid}.png").is_file() and (media / "logos" / f"{cid}.png").is_file()
    assert not (media / "logos" / "n64.png").exists()
    # the 8-bit NES logo is drawn smaller than the 16-bit SNES one
    assert QImage(str(media / "logos" / "nes.png")).width() < QImage(str(media / "logos" / "snes.png")).width()
    assert seen[-1] == (3, 3)


def test_a_download_that_isnt_a_picture_is_a_failure_not_a_crash(qapp, tmp_path, monkeypatch):
    with_sources(monkeypatch, tmp_path, {"nes": ["notapicture.svg"]})
    result = logos.fetch_logos(tmp_path / "media", fetcher=FakeFetcher(make_logo()), pause=0)
    assert result.done == [] and "nes" in result.failed
    assert not (tmp_path / "media" / "logos" / "source" / "nes.png").exists()  # no junk left behind


def test_logos_can_be_redrawn_from_the_saved_originals(qapp, tmp_path):
    media = tmp_path / "media"
    (media / "logos" / "source").mkdir(parents=True)
    make_logo(media / "logos" / "source" / "psx.png")
    out = logos.render_logo(media, "psx")
    assert out.is_file() and QImage(str(out)).width() <= eras.STYLES["32-bit"].width + 2
    with pytest.raises(EmulatorError):
        logos.render_logo(media, "nes")  # nothing saved for it


def test_downloads_may_only_come_from_wikimedia():
    fetcher = logos._fetcher()
    fetcher.check_url("https://en.wikipedia.org/wiki/Special:FilePath/NES_logo.svg?width=600")
    fetcher.check_url("https://thumb.wikimedia.org/x.png")
    with pytest.raises(EmulatorError):
        fetcher.check_url("https://example.com/logo.png")
    with pytest.raises(EmulatorError):
        fetcher.check_url("http://en.wikipedia.org/x.png")


def test_the_list_of_logo_files_covers_known_consoles_and_is_well_formed():
    data = logos.sources()
    assert data, "no logo sources listed"
    for cid, names in data.items():
        assert cid in eras.ERA_OF, cid
        assert names and all(isinstance(n, str) and n and "/" not in n and not n.startswith("File:") for n in names), cid


def test_a_downloaded_logo_is_used_but_never_over_your_own_picture(qapp, tmp_path):
    logo_dir, mine = tmp_path / "logos", tmp_path / "mine"
    logo_dir.mkdir()
    mine.mkdir()
    make_logo().scaled(90, 40).save(str(logo_dir / "nes.png"))
    try:
        pixelart.configure(None, logo_dir)
        assert pixelart.is_logo("nes") and pixelart.sprite_image("nes").width() == 90
        assert not pixelart.is_logo("snes")  # no logo downloaded for it: the plain cartridge
        assert not pixelart.is_bundled("snes") and pixelart.sprite_image("snes").size() == pixelart.sprite_image("anything-else").size()
        solid = QImage(70, 50, QImage.Format.Format_ARGB32)
        solid.fill(QColor("#3366cc"))
        solid.save(str(mine / "nes.png"))
        pixelart.configure(mine, logo_dir)
        assert pixelart.sprite_image("nes").width() == 70  # your own file wins over a logo
    finally:
        pixelart.configure(None, None)


def test_first_run_offers_the_logos_once(qapp, tmp_path, monkeypatch):
    from arcadia.config import Config
    from arcadia.library import Library
    from arcadia.ui import MainWindow

    cfg = Config.new_install(tmp_path / "A")
    cfg.ensure_layout()
    assert cfg.logos_asked is False
    win = MainWindow(cfg, tmp_path / "config.json", Library(cfg.db_path))
    asked = []
    monkeypatch.setattr(win, "download_logos", lambda: asked.append(1))
    try:
        win._offer_logos()
        win._offer_logos()
        assert asked == [1] and cfg.logos_asked is True
        assert '"logos_asked": true' in (tmp_path / "config.json").read_text()
    finally:
        win.close()
        pixelart.configure(None, None)


def test_a_too_many_requests_answer_is_retried(qapp, tmp_path, monkeypatch):
    with_sources(monkeypatch, tmp_path, {"nes": ["NES_logo.svg"]})

    class Busy(FakeFetcher):
        def download(self, url, dest, progress=None):
            self.asked.append(url)
            if len(self.asked) < 3:
                raise EmulatorError("the download server answered 429 Too many requests")
            self.picture.save(str(dest))

    fetcher = Busy(make_logo())
    result = logos.fetch_logos(tmp_path / "media", fetcher=fetcher, pause=0)
    assert result.done == ["nes"] and len(fetcher.asked) == 3 and len(set(fetcher.asked)) == 1  # the same address, three times


def test_check_custom_pictures(tmp_path):
    from PySide6.QtGui import QColor, QImage

    from arcadia import pixelart

    good = QImage(300, 200, QImage.Format.Format_ARGB32)
    good.fill(QColor("red"))
    good.save(str(tmp_path / "nes.png"))
    tiny = QImage(20, 20, QImage.Format.Format_ARGB32)
    tiny.fill(QColor("red"))
    tiny.save(str(tmp_path / "snes.png"))
    good.save(str(tmp_path / "bogus.png"))
    (tmp_path / "gc.png").write_text("not a picture")
    (tmp_path / "notes.txt").write_text("x")
    text = "\n".join(pixelart.check_custom(tmp_path, {"nes", "snes", "gc"}))
    assert "snes.png: only 20" in text and "bogus.png" in text and "gc.png: can't be read" in text and "notes.txt" in text
    assert "nes.png" not in text.replace("snes.png", "")
    assert pixelart.check_custom(None, set()) == []
