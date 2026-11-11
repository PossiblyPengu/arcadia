"""Shared Qt helpers for the interface tests."""

from PySide6.QtCore import QObject, Signal


class SyncTask(QObject):
    """Stands in for the background thread, so a test can run a whole flow in order."""

    progress = Signal(int, int)
    done = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self):
        try:
            value, error = self._fn(self.progress.emit), None
        except Exception as exc:
            value, error = None, exc
        self.done.emit(value, error)
