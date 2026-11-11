"""Run work off the interface thread so windows never freeze."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    """Run a function in the background. It is given a progress callback (done, total)."""

    progress = Signal(int, int)
    done = Signal(object, object)  # (result, error)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            value, error = self._fn(self.progress.emit), None
        except Exception as exc:  # reported to the user, never lost inside a thread
            value, error = None, exc
        self.done.emit(value, error)
