from __future__ import annotations

import argparse
import sys

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
    args, qt_args = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Arcadia")
    apply_dark_theme(app)

    config = Config.load(CONFIG_PATH)
    library = Library(config.db_path)
    window = MainWindow(config, CONFIG_PATH, library)
    if args.fullscreen:
        window.toggle_fullscreen()
    else:
        window.show()
    return app.exec()
