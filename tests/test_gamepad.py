import os
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from arcadia import gamepad as g

EV_KEY, EV_ABS = g.EV_KEY, g.EV_ABS


def test_buttons_map_to_actions_on_press_only():
    d = g.Decoder()
    assert d.feed(EV_KEY, g.BTN_SOUTH, 1, 0) == ["confirm"]
    assert d.feed(EV_KEY, g.BTN_SOUTH, 0, 0) == []  # release does nothing
    assert d.feed(EV_KEY, g.BTN_EAST, 1, 0) == ["back"]
    assert d.feed(EV_KEY, g.BTN_NORTH, 1, 0) == ["favorite"] and d.feed(EV_KEY, g.BTN_WEST, 1, 0) == ["favorite"]
    assert d.feed(EV_KEY, g.BTN_TL, 1, 0) == ["prev_system"] and d.feed(EV_KEY, g.BTN_TR, 1, 0) == ["next_system"]
    assert d.feed(EV_KEY, g.BTN_START, 1, 0) == ["options"] and d.feed(EV_KEY, g.BTN_SELECT, 1, 0) == ["options"]
    assert d.feed(EV_KEY, 0x999, 1, 0) == []


def test_dpad_hat_and_buttons_repeat_while_held():
    d = g.Decoder()
    assert d.feed(EV_ABS, g.ABS_HAT0X, 1, 0.0) == ["right"]
    assert d.repeats(0.2) == []  # not yet
    assert d.repeats(0.5) == ["right"]  # first repeat after 0.4 s
    assert d.repeats(0.55) == [] and d.repeats(0.7) == ["right"]  # then every 0.12 s
    d.feed(EV_ABS, g.ABS_HAT0X, 0, 0.8)
    assert d.repeats(5.0) == [] and d.next_due(5.0) is None
    assert d.feed(EV_ABS, g.ABS_HAT0Y, -1, 1.0) == ["up"]
    assert d.feed(EV_KEY, 0x223, 1, 1.0) == ["right"]  # a pad that reports the D-pad as buttons


def test_left_stick_needs_a_real_push_and_lets_go_with_hysteresis():
    d = g.Decoder({g.ABS_X: (-32768, 32767), g.ABS_Y: (0, 255)})
    assert d.feed(EV_ABS, g.ABS_X, 8000, 0) == []  # a slight lean is ignored
    assert d.feed(EV_ABS, g.ABS_X, 25000, 0) == ["right"]
    assert d.feed(EV_ABS, g.ABS_X, 18000, 0.1) == []  # still pushed: no second press
    assert d.held  # and it repeats
    d.feed(EV_ABS, g.ABS_X, 2000, 0.2)
    assert not d.held
    assert d.feed(EV_ABS, g.ABS_X, -30000, 0.3) == ["left"]
    assert d.feed(EV_ABS, g.ABS_Y, 20, 0.3) == ["up"]  # an unsigned 0..255 stick centres at 127
    assert d.feed(EV_ABS, g.ABS_Y, 128, 0.4) == [] and "up" not in d.held


def test_parse_events_reads_whole_input_event_records():
    size = struct.calcsize("@llHHi")
    one = struct.pack("@llHHi", 1, 2, EV_KEY, g.BTN_SOUTH, 1)
    two = struct.pack("@llHHi", 1, 3, EV_ABS, g.ABS_HAT0Y, -1)
    assert size == len(one)
    assert g.parse_events(one + two + b"junk") == [(EV_KEY, g.BTN_SOUTH, 1), (EV_ABS, g.ABS_HAT0Y, -1)]
    assert g.parse_events(b"") == []


def test_no_input_devices_is_quiet(qapp=None):
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.instance() or QCoreApplication([])
    reader = g.ControllerReader(pattern="/nonexistent/event*")
    seen = []
    reader.action.connect(seen.append)
    reader.problem.connect(seen.append)
    reader.start()
    reader.stop()
    assert seen == []

