"""Small sound effects: a tick when the console ring turns, a chime when you open something, a soft fall
when you go back. The files in assets/sounds are tiny generated tones (tools/make_sounds.py).

Sound is never required: with no audio device, no Qt multimedia, or the setting off, everything here quietly does nothing.
"""

from __future__ import annotations

import time
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets" / "sounds"
NAMES = ("tick", "open", "back")
VOLUME = 0.35
MIN_GAP = 0.03  # seconds: a fast spin doesn't machine-gun the tick


class Sounds:
    def __init__(self, enabled: bool = True, folder: Path = ASSETS):
        self.enabled = enabled
        self.folder = folder
        self._effects: dict[str, object] = {}
        self._broken = False
        self._last: dict[str, float] = {}

    def _effect(self, name: str):
        if name in self._effects:
            return self._effects[name]
        effect = None
        path = self.folder / f"{name}.wav"
        if path.is_file():
            try:
                from PySide6.QtCore import QUrl
                from PySide6.QtMultimedia import QSoundEffect

                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setVolume(VOLUME)
            except Exception:  # no multimedia support: carry on silently
                effect = None
                self._broken = True
        self._effects[name] = effect
        return effect

    def play(self, name: str) -> bool:
        """Play a sound if sound is on. Returns whether it was asked to play (it may still be silent without audio)."""
        if not self.enabled or self._broken or name not in NAMES:
            return False
        now = time.monotonic()
        if now - self._last.get(name, 0.0) < MIN_GAP:
            return False
        self._last[name] = now
        effect = self._effect(name)
        if effect is None:
            return False
        try:
            effect.play()
        except Exception:
            return False
        return True
