"""Keep every dialog on the screen: on a Steam Deck (1280 x 800, less in Desktop Mode) a window sized for a
desktop monitor would hang off the edge. Install once; any dialog taller or wider than the screen is shrunk
to fit as it appears."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QDialog


class _Fitter(QObject):
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt's name)
        if event.type() == QEvent.Type.Show and isinstance(obj, QDialog) and obj.isWindow():
            fit(obj)
        return False


def fit(dialog: QDialog, share_w: float = 0.96, share_h: float = 0.92) -> None:
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    avail = screen.availableGeometry()
    width = min(dialog.width(), int(avail.width() * share_w))
    height = min(dialog.height(), int(avail.height() * share_h))
    if (width, height) != (dialog.width(), dialog.height()):
        dialog.resize(width, height)
        dialog.move(avail.x() + (avail.width() - width) // 2, avail.y() + (avail.height() - height) // 2)


def install(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is not None and not getattr(app, "_arcadia_screenfit", None):
        app._arcadia_screenfit = _Fitter(app)  # kept alive by the application
        app.installEventFilter(app._arcadia_screenfit)
