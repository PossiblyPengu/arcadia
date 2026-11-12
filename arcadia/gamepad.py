"""Controller input, read straight from Linux's /dev/input: no Steam Input layout and no extra packages needed.

In Game Mode a Steam Deck's buttons reach a program as an ordinary gamepad (Steam presents it as a virtual Xbox
controller) and Arcadia reads that itself: D-pad and left stick to move, A to choose, B to go back, X or Y for
favorite, the bumpers to change console, and Menu / Start (or View / Select) for the Options list. New controllers
are noticed while Arcadia runs. On the desktop, Steam turns the Deck's controls into keyboard keys instead, and
the window handles those, so both ways work.
"""

from __future__ import annotations

import fcntl
import glob
import os
import select
import struct
import threading
import time

from PySide6.QtCore import QThread, Signal

# Linux input event codes (linux/input-event-codes.h)
EV_KEY, EV_ABS = 0x01, 0x03
BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_TL, BTN_TR, BTN_SELECT, BTN_START, BTN_MODE = 0x136, 0x137, 0x13A, 0x13B, 0x13C
BTN_DPAD = {0x220: "up", 0x221: "down", 0x222: "left", 0x223: "right"}
ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0x00, 0x01, 0x10, 0x11

BUTTON_ACTIONS = {
    "BTN_SOUTH": "confirm",  # A / Cross
    "BTN_EAST": "back",  # B / Circle
    "BTN_NORTH": "favorite",  # X on an Xbox layout, Triangle on PlayStation
    "BTN_WEST": "favorite",  # Y on an Xbox layout
    "BTN_TL": "prev_system",  # left bumper
    "BTN_TR": "next_system",  # right bumper
    "BTN_START": "options",  # Menu / Start: the Options list
    "BTN_SELECT": "options",  # View / Select
}
_CODE_ACTIONS = {
    BTN_SOUTH: "confirm", BTN_EAST: "back", BTN_NORTH: "favorite", BTN_WEST: "favorite",
    BTN_TL: "prev_system", BTN_TR: "next_system", BTN_START: "options", BTN_SELECT: "options",
}

REPEAT_FIRST = 0.40  # a held direction repeats after this many seconds...
REPEAT_EVERY = 0.12  # ...and then this often
STICK_ON = 0.55  # how far (of full travel) the stick must go to count as a press
STICK_OFF = 0.35  # and how far back it must come to let go


class Decoder:
    """Turns raw (type, code, value) events from one controller into actions, with repeat for held directions."""

    def __init__(self, stick_range: dict[int, tuple[int, int]] | None = None):
        self.ranges = stick_range or {}
        self.held: dict[str, float] = {}  # direction -> when it next repeats
        self._stick: dict[int, str | None] = {ABS_X: None, ABS_Y: None}

    def feed(self, ev_type: int, code: int, value: int, now: float) -> list[str]:
        out: list[str] = []
        if ev_type == EV_KEY:
            if code in BTN_DPAD:
                self._direction(BTN_DPAD[code], value != 0, now, out)
            elif value == 1 and code in _CODE_ACTIONS:
                out.append(_CODE_ACTIONS[code])
        elif ev_type == EV_ABS:
            if code == ABS_HAT0X:
                self._direction("left", value < 0, now, out)
                self._direction("right", value > 0, now, out)
            elif code == ABS_HAT0Y:
                self._direction("up", value < 0, now, out)
                self._direction("down", value > 0, now, out)
            elif code in (ABS_X, ABS_Y):
                self._stick_moved(code, value, now, out)
        return out

    def _direction(self, name: str, down: bool, now: float, out: list[str]) -> None:
        if down and name not in self.held:
            self.held[name] = now + REPEAT_FIRST
            out.append(name)
        elif not down:
            self.held.pop(name, None)

    def _stick_moved(self, code: int, value: int, now: float, out: list[str]) -> None:
        lo, hi = self.ranges.get(code, (-32768, 32767))
        mid, half = (lo + hi) / 2, max(1.0, (hi - lo) / 2)
        pos = (value - mid) / half
        names = ("left", "right") if code == ABS_X else ("up", "down")
        current = self._stick[code]
        if current is not None:  # already pushed one way: let go only once it's well back towards the middle
            if abs(pos) < STICK_OFF or (pos < 0) != (current == names[0]):
                self._direction(current, False, now, out)
                self._stick[code] = None
                current = None
            else:
                return
        if abs(pos) >= STICK_ON:
            name = names[0] if pos < 0 else names[1]
            self._stick[code] = name
            self._direction(name, True, now, out)

    def repeats(self, now: float) -> list[str]:
        out = []
        for name, due in list(self.held.items()):
            if now >= due:
                self.held[name] = now + REPEAT_EVERY
                out.append(name)
        return out

    def next_due(self, now: float) -> float | None:
        return max(0.0, min(self.held.values()) - now) if self.held else None


# ----- finding and reading the devices -----

_EVENT = struct.Struct("@llHHi")  # time (seconds, microseconds), type, code, value


def _ioc_read(nr: int, size: int) -> int:
    return (2 << 30) | (size << 16) | (ord("E") << 8) | nr


def _has_bit(fd: int, ev_type: int, code: int) -> bool:
    size = code // 8 + 1
    buf = bytearray(max(size, 96))
    try:
        fcntl.ioctl(fd, _ioc_read(0x20 + ev_type, len(buf)), buf)
    except OSError:
        return False
    return bool(buf[code // 8] & (1 << (code % 8)))


def is_gamepad(fd: int) -> bool:
    """A controller has a south face button (A); keyboards, mice and touchpads don't."""
    return _has_bit(fd, EV_KEY, BTN_SOUTH)


def stick_ranges(fd: int) -> dict[int, tuple[int, int]]:
    out = {}
    for code in (ABS_X, ABS_Y):
        buf = bytearray(24)  # struct input_absinfo: value, minimum, maximum, fuzz, flat, resolution
        try:
            fcntl.ioctl(fd, _ioc_read(0x40 + code, 24), buf)
        except OSError:
            continue
        _value, lo, hi = struct.unpack_from("@iii", buf)
        if hi > lo:
            out[code] = (lo, hi)
    return out


def parse_events(data: bytes) -> list[tuple[int, int, int]]:
    """(type, code, value) for each whole event in what was read."""
    return [struct.unpack_from("@HHi", data, off + 16)[0:3] for off in range(0, len(data) - _EVENT.size + 1, _EVENT.size)]


class ControllerReader(QThread):
    action = Signal(str)
    problem = Signal(str)  # a controller was found but couldn't be read (permissions), said once

    def __init__(self, parent=None, pattern: str = "/dev/input/event*"):
        super().__init__(parent)
        self._running = True
        self._wake = threading.Event()
        self._pattern = pattern
        self._told = False

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        self.wait(2000)

    def _scan(self, open_paths: dict[str, tuple[int, Decoder]]) -> None:
        denied = opened = 0
        for path in sorted(glob.glob(self._pattern)):
            if path in open_paths:
                opened += 1
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                denied += 1
                continue
            except OSError:
                continue
            opened += 1
            if is_gamepad(fd):
                open_paths[path] = (fd, Decoder(stick_ranges(fd)))
            else:
                os.close(fd)
        if denied and not opened and not self._told:  # every input device is off limits: say so, once
            self._told = True
            self.problem.emit(
                "Arcadia isn't allowed to read the controller. Add your user to the “input” group "
                "(sudo usermod -aG input $USER, then log out and in), or use Steam's controller layout."
            )

    def run(self) -> None:
        devices: dict[str, tuple[int, Decoder]] = {}
        next_scan = 0.0
        try:
            while self._running:
                now = time.monotonic()
                if now >= next_scan:
                    self._scan(devices)
                    next_scan = now + (2.0 if devices else 1.0)
                fds = {fd: (path, dec) for path, (fd, dec) in devices.items()}
                waits = [d for d in (dec.next_due(now) for _fd, dec in fds.values()) if d is not None]
                timeout = min([0.5, *waits]) if waits else 0.5
                if not fds:
                    self._wake.wait(0.5)
                    continue
                try:
                    ready, _, _ = select.select(list(fds), [], [], timeout)
                except (OSError, ValueError):
                    ready = []
                now = time.monotonic()
                for fd in ready:
                    path, dec = fds[fd]
                    try:
                        data = os.read(fd, _EVENT.size * 64)
                    except BlockingIOError:
                        continue
                    except OSError:  # unplugged
                        os.close(fd)
                        devices.pop(path, None)
                        continue
                    for ev_type, code, value in parse_events(data):
                        for name in dec.feed(ev_type, code, value, now):
                            self.action.emit(name)
                for _fd, dec in fds.values():
                    for name in dec.repeats(now):
                        self.action.emit(name)
        finally:
            for fd, _dec in devices.values():
                try:
                    os.close(fd)
                except OSError:
                    pass
