from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from arcadia.config import CONFIG_PATH, Config
from arcadia.library import Library


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(28, 30, 36))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(230, 232, 238))
    palette.setColor(QPalette.ColorRole.Base, QColor(20, 22, 27))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(36, 39, 46))
    palette.setColor(QPalette.ColorRole.Text, QColor(230, 232, 238))
    palette.setColor(QPalette.ColorRole.Button, QColor(44, 48, 57))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(230, 232, 238))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(62, 137, 214))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)


def main(argv: list[str] | None = None) -> int:
    from arcadia.ui import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Arcadia")
    apply_dark_theme(app)

    config = Config.load(CONFIG_PATH)
    library = Library(config.db_path)
    window = MainWindow(config, CONFIG_PATH, library)
    window.show()
    return app.exec()
