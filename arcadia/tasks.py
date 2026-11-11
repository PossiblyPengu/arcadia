"""Run work off the interface thread so windows never freeze."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal


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


class DaemonTask(QObject):
    """Like Task, but on a daemon thread, so it can never keep Arcadia from closing. For things that
    don't matter if they're cut short, such as a check for updates at startup.

    Connect `done` to a method of a QObject (not a bare lambda), so the result is delivered on the
    interface thread."""

    done = Signal(object, object)  # (result, error)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="arcadia-task").start()

    def _run(self) -> None:
        try:
            value, error = self._fn(), None
        except Exception as exc:
            value, error = None, exc
        self.done.emit(value, error)
