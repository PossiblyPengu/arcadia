from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from arcadia.config import CONFIG_PATH, Config
from arcadia.library import Library


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(20, 21, 27))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(236, 238, 244))
    palette.setColor(QPalette.ColorRole.Base, QColor(24, 25, 32))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(32, 34, 42))
    palette.setColor(QPalette.ColorRole.Text, QColor(236, 238, 244))
    palette.setColor(QPalette.ColorRole.Button, QColor(44, 48, 57))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(236, 238, 244))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(62, 137, 214))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)


def main(argv: list[str] | None = None) -> int:
    from arcadia.ui import MainWindow

    parser = argparse.ArgumentParser(prog="arcadia", description="Emulator launcher and ROM library manager")
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen (handy on a Steam Deck)")
    parser.add_argument(
        "--home",
        type=Path,
        help="run entirely from this folder: its config.json, ROMs, emulators and saves, so it can be moved or "
        "carried on a drive (also read from the ARCADIA_HOME environment variable)",
    )
    args, qt_args = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Arcadia")
    apply_dark_theme(app)

    home = args.home or (Path(os.environ["ARCADIA_HOME"]) if os.environ.get("ARCADIA_HOME") else None)
    if home is not None:
        home = home.expanduser().resolve()
    config_path = home / "config.json" if home is not None else CONFIG_PATH
    first_run = not config_path.exists()
    config = Config.load(config_path, home=home)
    if first_run:  # set up the Arcadia folder the first time, so there's somewhere to put ROMs
        config.ensure_layout()
        config.save(config_path)
    library = Library(config.db_path)
    window = MainWindow(config, config_path, library)
    if args.fullscreen:
        window.toggle_fullscreen()
    else:
        window.show()
    if first_run:  # a new setup: walk through what's needed
        QTimer.singleShot(400, window.show_welcome)
    return app.exec()
