"""Controller input via Linux evdev.

Steam Input already maps a Steam Deck's controls to keyboard keys, so the UI
works with the keyboard alone. This reader is an extra path for plain gamepads
that show up as evdev devices. If the evdev package is missing, or no gamepad
is found, it does nothing.
"""

from __future__ import annotations

import selectors

from PySide6.QtCore import QThread, Signal

BUTTON_ACTIONS = {
    "BTN_SOUTH": "confirm",  # A / Cross
    "BTN_EAST": "back",  # B / Circle
    "BTN_NORTH": "favorite",  # Y / Triangle
    "BTN_TL": "prev_system",  # left bumper
    "BTN_TR": "next_system",  # right bumper
}
HAT_ACTIONS = {
    ("ABS_HAT0X", -1): "left",
    ("ABS_HAT0X", 1): "right",
    ("ABS_HAT0Y", -1): "up",
    ("ABS_HAT0Y", 1): "down",
}


def _names(ecodes, code: int, ev_type: int) -> list[str]:
    name = ecodes.bytype.get(ev_type, {}).get(code, [])
    return name if isinstance(name, list) else [name]


class ControllerReader(QThread):
    action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def run(self) -> None:
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            return

        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.BTN_SOUTH in keys:
                devices.append(dev)
            else:
                dev.close()
        if not devices:
            return

        selector = selectors.DefaultSelector()
        for dev in devices:
            selector.register(dev, selectors.EVENT_READ)
        try:
            while self._running:
                for key, _ in selector.select(timeout=0.5):
                    dev = key.fileobj
                    try:
                        events = list(dev.read())
                    except (BlockingIOError, OSError):
                        continue
                    for ev in events:
                        name = self._translate(ecodes, ev)
                        if name:
                            self.action.emit(name)
        finally:
            for dev in devices:
                try:
                    selector.unregister(dev)
                except (KeyError, ValueError):
                    pass
                dev.close()
            selector.close()

    @staticmethod
    def _translate(ecodes, ev) -> str | None:
        if ev.type == ecodes.EV_KEY and ev.value == 1:
            for name in _names(ecodes, ev.code, ecodes.EV_KEY):
                if name in BUTTON_ACTIONS:
                    return BUTTON_ACTIONS[name]
        elif ev.type == ecodes.EV_ABS and ev.value in (-1, 1):
            for name in _names(ecodes, ev.code, ecodes.EV_ABS):
                if (name, ev.value) in HAT_ACTIONS:
                    return HAT_ACTIONS[(name, ev.value)]
        return None
