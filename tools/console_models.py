"""Every console as a 3D drawing in real centimetres (tools/isoart.py). The generation each belongs to is in arcadia/eras.py.

The shapes, proportions and details follow the real hardware (checked against photographs while drawing); the
drawing is then reduced to the pixel style of its era by make_console_art.py. Colours are original picks.
"""

from __future__ import annotations

from arcadia.eras import era_of
from isoart import Scene


# ---------------------------------------------------------------- 8-bit

def nes(s: Scene) -> None:
    base = s.box(0, 0, 0, 25.6, 19.7, 4.0, "#8d8d88", r=0.5)
    shell = s.box(0, 0, 4.0, 25.6, 19.7, 5.5, "#d2d2cc", r=0.7)
    s.ff(shell, 0.06, 0.12, 0.74, 0.88, "#c6c6c0")  # the cartridge lid, slightly darker
    s.ff(shell, 0.09, 0.56, 0.31, 0.64, "#b8504a")  # the red lettering
    s.ff(shell, 0.09, 0.38, 0.28, 0.44, "#b8504a")
    s.ff(shell, 0.79, 0, 1.0, 1.0, "#26262c")  # the black block at the right end of the front
    s.ff(base, 0.79, 0, 1.0, 1.0, "#1f1f23")
    s.ff(base, 0.83, 0.18, 0.95, 0.62, "#0e0e11")  # the controller port
    s.ft(shell, 0.78, 0.80, 0.97, 1.0, "#303036")  # top strip: black block at the front,
    for i in range(10):  # ribs behind it,
        s.ft(shell, 0.78, 0.40 + i * 0.039, 0.97, 0.40 + i * 0.039 + 0.021, "#a4a49e")
    s.ft(shell, 0.78, 0.20, 0.97, 0.38, "#303036")  # and a black cap at the back
    s.ff(base, 0.15, 0.28, 0.26, 0.72, "#5e5e5a")  # power and reset
    s.ff(base, 0.29, 0.28, 0.40, 0.72, "#5e5e5a")


def gb(s: Scene) -> None:
    b = s.box(0, 0, 0, 9.0, 3.2, 14.8, "#c9c9c3", r=0.7)
    s.ff(b, 0.10, 0.42, 0.90, 0.94, "#6c6c74")  # the wide dark-grey screen surround
    s.ff(b, 0.10, 0.885, 0.90, 0.905, "#8a78b8")
    s.ff(b, 0.10, 0.845, 0.90, 0.865, "#5a5a9a")
    s.ff(b, 0.25, 0.52, 0.76, 0.81, "#a9c21a")  # the screen
    s.ff(b, 0.33, 0.58, 0.69, 0.74, "#9ab316")
    s.ff(b, 0.11, 0.25, 0.40, 0.32, "#1c1c22")  # the cross
    s.ff(b, 0.21, 0.19, 0.30, 0.38, "#1c1c22")
    s.fcf(b, 0.82, 0.26, 0.72, "#9c2f66")  # B and A
    s.fcf(b, 0.64, 0.21, 0.72, "#9c2f66")
    s.ff(b, 0.25, 0.10, 0.40, 0.13, "#8c8c92")  # select and start
    s.ff(b, 0.46, 0.08, 0.61, 0.11, "#8c8c92")
    for i in range(5):  # the speaker grille
        s.ff(b, 0.68 + i * 0.055, 0.04 + 0.012 * i, 0.70 + i * 0.055, 0.15 + 0.012 * i, "#a0a09a")


# ---------------------------------------------------------------- 16-bit

def snes(s: Scene) -> None:
    body = s.box(0, 0, 0, 23.0, 20.5, 6.4, "#cfcfd5", r=0.9)
    s.ff(body, 0, 0, 1, 0.22, "#b8b8c2")
    lid = s.box(3.2, 0.7, 6.4, 16.6, 9.6, 0.5, "#c5c5cd")  # the cartridge lid at the back
    s.ft(lid, 0.12, 0.14, 0.88, 0.34, "#aeaeb8")
    s.ft(body, 0.40, 0.56, 0.62, 1.0, "#bcbcc6")  # the grey eject plate running to the front
    s.ft(body, 0.21, 0.52, 0.40, 0.68, "#7b57c8")  # power
    s.ft(body, 0.62, 0.60, 0.84, 0.76, "#7b57c8")  # reset
    s.ff(body, 0.10, 0.26, 0.20, 0.56, "#4e4e58")  # controller ports
    s.ff(body, 0.22, 0.26, 0.32, 0.56, "#4e4e58")
    s.ff(body, 0.385, 0, 0.40, 1, "#a8a8b2")  # the front is in three sections
    s.ff(body, 0.66, 0, 0.68, 1, "#a8a8b2")
    s.ff(body, 0.74, 0.20, 0.90, 0.42, "#2a2a30")  # the expansion connector


def genesis(s: Scene) -> None:
    body = s.box(0, 0, 0, 28.0, 21.0, 5.6, "#222228", r=0.7)
    back = s.box(0, 0, 5.6, 28.0, 8.5, 1.3, "#25252b", r=0.4)
    for i in range(8):  # the ribbed grille at the back left
        s.ft(back, 0.03 + i * 0.026, 0.12, 0.03 + i * 0.026 + 0.012, 0.92, "#101014")
    ring = s.disc(19.0, 8.6, 5.6, 6.6, 1.7, "#2a2a30", taper=0.97, top="#303038")  # the cartridge ring
    rb = (19.0 - 6.6, 8.6 - 6.6, 5.6, 13.2, 13.2, 1.7)
    s.c_top(rb, 6.6, 6.6, 5.8, "#18181d")
    s.d_top(rb, 2.0, 1.2, 11.2, 2.4, "#0c0c10")  # the cartridge slot
    s.d_top(rb, 4.0, 5.2, 9.2, 10.0, "#17171b")  # the label
    s.d_top(rb, 4.6, 6.4, 8.6, 8.2, "#d9b04a")  # 16-BIT
    s.d_top(rb, 3.0, 10.2, 10.2, 11.5, "#9b2a68")  # the magenta strip
    s.d_top(body, 5.6, 9.0, 6.6, 16.0, "#101014")  # the power and volume sliders
    s.d_top(body, 7.4, 9.0, 8.4, 14.0, "#101014")
    s.d_top(body, 9.4, 14.0, 12.0, 15.6, "#2f6fd6")  # reset
    s.ff(body, 0.10, 0.45, 0.14, 0.65, "#0c0c10")  # headphone socket
    s.ff(body, 0.60, 0.25, 0.80, 0.40, "#c8c8d0")  # the maker's name
    s.ff(body, 0.83, 0.30, 0.93, 0.62, "#0c0c10")  # the extra port


# ---------------------------------------------------------------- 32-bit

def psx(s: Scene) -> None:
    body = s.box(0, 0, 0, 27.0, 19.5, 6.0, "#a9a9a5", r=0.8, top="#b2b2ae")
    s.disc(11.8, 9.6, 6.0, 7.6, 0.9, "#a5a5a1", taper=0.98, top="#b0b0ac")  # the disc lid
    lb = (4.2, 2.0, 6.0, 15.2, 15.2, 0.9)
    s.c_top(lb, 7.6, 7.6, 5.4, "#aeaeaa")
    s.c_top(body, 3.0, 8.4, 1.5, "#98aaa6")  # power
    s.c_top(body, 24.3, 15.4, 1.5, "#98aaa6")  # open
    s.ff(body, 0.40, 0.12, 0.58, 0.42, "#6b6b6b")  # memory card slot
    s.ff(body, 0.62, 0.12, 0.90, 0.38, "#4a4a4a")  # controller port
    s.ff(body, 0.66, 0.20, 0.86, 0.30, "#232323")
    for i in range(14):  # the vents on the right end
        s.fs(body, 0.10 + i * 0.062, 0.12, 0.10 + i * 0.062 + 0.026, 0.62, "#8c8c88")


def saturn(s: Scene) -> None:
    body = s.box(0, 0, 0, 26.0, 23.5, 7.4, "#1c1c21", r=1.2, top="#222228")
    s.ft(body, 0.15, 0.03, 0.85, 0.09, "#26262c")
    s.disc(10.6, 11.8, 7.4, 8.6, 0.8, "#17171b", taper=0.98, top="#1c1c21")  # the disc cover
    cb = (2.0, 3.2, 7.4, 17.2, 17.2, 0.8)
    s.c_top(cb, 8.6, 3.2, 1.0, "#2a2a31")  # the little bump at the back of it
    s.ff(body, 0.07, 0.30, 0.15, 0.46, "#d0d0d8")  # the maker's name
    s.ff(body, 0.22, 0.38, 0.27, 0.46, "#33333a")  # power, reset, open
    s.ff(body, 0.30, 0.38, 0.35, 0.46, "#33333a")
    s.ff(body, 0.38, 0.38, 0.43, 0.46, "#33333a")
    s.ff(body, 0.58, 0.12, 0.76, 0.26, "#2c2c33")  # the cartridge slot
    for j in range(4):  # the vent grille on the right
        for i in range(8):
            s.fs(body, 0.45 + i * 0.05, 0.30 + j * 0.15, 0.45 + i * 0.05 + 0.03, 0.30 + j * 0.15 + 0.10, "#0e0e12")


# ---------------------------------------------------------------- 64-bit

def n64(s: Scene) -> None:
    s.disc(16.0, 12.2, 0, 4.3, 2.4, "#17171b", taper=0.95)  # the round foot
    body = s.box(0, 0, 2.2, 26.0, 19.0, 4.6, "#4a4a52", r=3.8, top="#54545c")
    hump = s.box(5.2, 0.6, 6.8, 15.6, 8.6, 1.7, "#4a4a52", r=1.8, top="#54545c")  # the raised cartridge housing
    s.ft(hump, 0.10, 0.10, 0.90, 0.52, "#2a2a31")
    for i in range(9):  # ribs on the slot
        s.ft(hump, 0.16 + i * 0.075, 0.16, 0.16 + i * 0.075 + 0.03, 0.48, "#43434b")
    s.ft(hump, 0.12, 0.62, 0.88, 0.80, "#0c0c10")
    s.ft(body, 0.14, 0.58, 0.28, 0.84, "#2a2a31")  # the power switch
    s.ft(body, 0.36, 0.58, 0.57, 0.86, "#42424a")  # the expansion flap
    s.ft(body, 0.72, 0.64, 0.81, 0.82, "#33333a")  # reset
    s.ff(body, 0.05, 0.12, 0.95, 0.86, "#17171b")  # the dark front panel
    for x in (0.17, 0.31, 0.69, 0.83):  # two ports each side of the logo window
        s.fcf(body, x, 0.46, 1.15, "#b9b9c1")
        s.fcf(body, x, 0.46, 0.75, "#0b0b0e")
    s.ff(body, 0.41, 0.26, 0.59, 0.74, "#0b0b0e")  # the logo window
    s.ff(body, 0.45, 0.38, 0.51, 0.62, "#3e8f5a")
    s.ff(body, 0.51, 0.38, 0.55, 0.62, "#d6322c")


# ---------------------------------------------------------------- 128-bit

def gc(s: Scene) -> None:
    body = s.box(0, 0, 0, 15.0, 16.0, 10.4, "#4e3fa6", r=0.7, top="#5b4bb5")
    s.box(6.6, 0.0, 10.4, 7.2, 1.4, 1.1, "#17171c", r=0.5)  # the handle, seen behind
    s.disc(9.2, 8.9, 10.4, 4.9, 0.2, "#17171c", top="#0f0f13")  # the black disc lid
    s.ft(body, 0.70, 0.06, 0.93, 0.15, "#2f2f3a")  # the logo window
    s.fct(body, 0.17, 0.12, 0.9, "#ececf2")  # the open button
    s.ff(body, 0.04, 0.12, 0.82, 0.60, "#ebebf3")  # the white front panel
    for x in (0.16, 0.34, 0.52):  # three controller ports
        s.fcf(body, x, 0.36, 1.05, "#2b2b38")
    s.ff(body, 0.62, 0.24, 0.80, 0.48, "#cfcfda")  # memory card slot
    for i in range(8):  # the vent grid on the right face
        s.fs(body, 0.20 + i * 0.065, 0.40, 0.20 + i * 0.065 + 0.03, 0.84, "#2f2678")
    for j in range(6):
        s.fs(body, 0.20, 0.40 + j * 0.08, 0.66, 0.40 + j * 0.08 + 0.03, "#2f2678")


def dreamcast(s: Scene) -> None:
    body = s.box(0, 0, 0, 19.6, 19.4, 6.4, "#ecedef", r=1.6, top="#f4f5f6")
    s.disc(9.6, 9.5, 6.4, 7.9, 0.4, "#e7e9eb", taper=0.99, top="#eff1f2")  # the disc lid
    s.p_top(body, [(8.7, 14.2), (10.9, 14.2), (9.8, 16.6)], "#f9f9fb")  # the V on the lid
    s.fct(body, 0.66, 0.46, 1.0, "#f28a1a")  # the swirl
    s.fct(body, 0.11, 0.80, 1.3, "#d9dbdd")  # power
    s.fct(body, 0.88, 0.82, 1.3, "#d9dbdd")  # open
    for x in (0.31, 0.47, 0.63):  # three controller ports
        s.ff(body, x - 0.05, 0.20, x + 0.05, 0.52, "#3a3a42")
    s.ff(body, 0.38, 0.66, 0.56, 0.76, "#2d63b8")  # the maker's name
    for i in range(7):  # vents on the right face
        s.fs(body, 0.62 + i * 0.045, 0.14, 0.62 + i * 0.045 + 0.02, 0.50, "#c3c5c7")


# ---------------------------------------------------------------- the rest, by generation

def _keys(s: Scene, b, rows, x0: float, x1: float, y0: float, row_h: float, gap: float, color: str, per_row: int) -> None:
    """Rows of keys on a top face, by fraction."""
    width = (x1 - x0) / per_row
    for r in range(rows):
        for k in range(per_row):
            s.ft(b, x0 + k * width + gap, y0 + r * (row_h + gap * 1.4), x0 + (k + 1) * width - gap, y0 + r * (row_h + gap * 1.4) + row_h, color)


def sms(s: Scene) -> None:
    body = s.box(0, 0, 0, 37.5, 20.5, 6.5, "#1c1c20", r=0.9, top="#212126")
    s.ft(body, 0.05, 0.10, 0.30, 0.15, "#c9c9cf")  # the maker's name
    s.ft(body, 0.46, 0.30, 0.82, 0.74, "#d6322c")  # the red panel
    s.p_top(body, [(19.5, 9.0), (23.5, 9.0), (21.5, 12.4)], "#f2f2f2")  # its white triangle
    s.ft(body, 0.53, 0.04, 0.84, 0.24, "#08080a")  # the cartridge slot
    s.ff(body, 0.06, 0.52, 0.19, 0.72, "#d6322c")
    s.ff(body, 0.44, 0.18, 0.56, 0.60, "#08080a")  # controller ports
    s.ft(body, 0.88, 0.50, 0.95, 0.60, "#3a3a40")


def gbc(s: Scene) -> None:
    b = s.box(0, 0, 0, 7.8, 2.7, 13.3, "#9078cc", r=0.9, top="#a08ad8")
    s.ff(b, 0.10, 0.50, 0.90, 0.95, "#17171c")  # the black screen surround
    s.ff(b, 0.21, 0.60, 0.79, 0.88, "#8a9884")
    s.ff(b, 0.10, 0.50, 0.90, 0.54, "#22222a")
    s.ff(b, 0.10, 0.30, 0.33, 0.35, "#26262c")  # the cross
    s.ff(b, 0.19, 0.22, 0.24, 0.44, "#26262c")
    s.fcf(b, 0.80, 0.30, 0.55, "#26262c")  # B and A
    s.fcf(b, 0.64, 0.24, 0.55, "#26262c")
    s.ff(b, 0.14, 0.06, 0.34, 0.15, "#3f7a4a")  # the circuit board showing through
    for i in range(4):  # the speaker dots
        s.fcf(b, 0.66 + i * 0.07, 0.07 + 0.01 * i, 0.16, "#5a4a8a")


def atari2600(s: Scene) -> None:
    low = s.box(0, 0, 0, 32.0, 21.5, 4.8, "#1c1c20", r=0.5)
    s.ff(low, 0, 0, 1, 1, "#8a5a2b")  # the wood panel on the front
    s.ff(low, 0, 0.88, 1, 1, "#b07a40")
    mid = s.box(0, 0, 4.8, 32.0, 15.5, 2.2, "#1c1c20", r=0.4)
    for i in range(10):  # the ribbed deck
        s.ft(mid, 0.02, 0.06 + i * 0.092, 0.98, 0.06 + i * 0.092 + 0.036, "#0a0a0c")
    back = s.box(1.4, 0, 7.0, 29.2, 7.2, 2.3, "#222226", r=0.4)
    s.ft(back, 0.30, 0.25, 0.72, 0.42, "#3c3c42")  # the label
    s.ft(back, 0.36, 0.55, 0.64, 0.82, "#08080a")  # the cartridge slot
    for u in (0.10, 0.19, 0.78, 0.86):  # four switches
        s.ft(back, u, 0.35, u + 0.045, 0.62, "#c9c9ce")


def atari7800(s: Scene) -> None:
    body = s.box(0, 0, 0, 33.0, 22.0, 5.2, "#232327", r=0.7, top="#2a2a2f")
    s.ft(body, 0, 0.30, 1, 0.52, "#c9c9cc")  # the silver band
    for i, c in enumerate(("#d6322c", "#f28a1a", "#3fae5a", "#2d63b8")):  # with its coloured stripes
        s.ft(body, 0, 0.50 + i * 0.012, 1, 0.50 + i * 0.012 + 0.006, c)
    s.ft(body, 0.38, 0.06, 0.62, 0.30, "#08080a")  # the cartridge slot
    for i in range(8):
        s.ft(body, 0.06, 0.60 + i * 0.045, 0.34, 0.60 + i * 0.045 + 0.02, "#1a1a1e")
    s.ff(body, 0.06, 0.30, 0.20, 0.45, "#a0a0a8")


def gamegear(s: Scene) -> None:
    b = s.box(0, 0, 0, 21.0, 3.7, 11.1, "#202026", r=2.4, top="#2a2a30")
    s.ff(b, 0.27, 0.16, 0.69, 0.92, "#2e2e35")  # the screen surround
    s.ff(b, 0.30, 0.26, 0.66, 0.86, "#4a6a72")  # the screen
    s.fcf(b, 0.13, 0.55, 1.5, "#141418")  # the d-pad recess
    s.ff(b, 0.07, 0.52, 0.19, 0.58, "#3a3a42")
    s.ff(b, 0.11, 0.40, 0.15, 0.70, "#3a3a42")
    s.fcf(b, 0.82, 0.78, 0.55, "#2d63b8")  # start
    s.fcf(b, 0.85, 0.46, 0.95, "#101014")  # buttons 1 and 2
    s.fcf(b, 0.91, 0.28, 0.95, "#101014")
    s.ff(b, 0.73, 0.62, 0.84, 0.68, "#c8c8d0")  # the maker's name
    for i in range(4):  # the speaker
        for j in range(4):
            s.fcf(b, 0.11 + i * 0.022, 0.12 + j * 0.05, 0.14, "#0e0e12")


def msx(s: Scene) -> None:
    body = s.box(0, 0, 0, 40.0, 24.0, 5.0, "#1c1c20", r=1.2, top="#232327")
    s.ft(body, 0.20, 0.05, 0.56, 0.13, "#08080a")  # cartridge slots
    s.ft(body, 0.60, 0.05, 0.80, 0.13, "#08080a")
    for i in range(5):  # function keys
        s.ft(body, 0.07 + i * 0.075, 0.19, 0.07 + i * 0.075 + 0.062, 0.26, "#8cc4e8")
    s.ft(body, 0.82, 0.19, 0.89, 0.26, "#d6322c")
    _keys(s, body, 4, 0.09, 0.78, 0.31, 0.10, 0.004, "#c4e0ee", 14)
    s.ft(body, 0.80, 0.34, 0.94, 0.74, "#c4e0ee")  # the big cursor key
    s.ft(body, 0.24, 0.80, 0.62, 0.90, "#c4e0ee")  # the space bar
    s.ff(body, 0.42, 0.40, 0.58, 0.62, "#c9c9d0")


def ps2(s: Scene) -> None:
    s.box(-1.5, -0.8, 0, 21.0, 10.0, 2.4, "#2f6fd6", r=1.2)  # the blue stand
    body = s.box(0, 0, 2.4, 18.0, 7.8, 30.0, "#17171c", r=0.8, top="#202026")
    s.ff(body, 0.12, 0.20, 0.60, 0.30, "#3c5fa8")  # the logo
    s.ff(body, 0, 0.55, 1, 0.56, "#0e0e12")  # the disc tray seam
    for i in range(9):  # the ridges on the side
        s.fs(body, 0.10 + i * 0.09, 0.25, 0.10 + i * 0.09 + 0.04, 0.85, "#0e0e12")
    s.ff(body, 0.70, 0.62, 0.86, 0.65, "#4a4a52")


def psp(s: Scene) -> None:
    b = s.box(0, 0, 0, 17.0, 2.3, 7.4, "#16161a", r=1.5, top="#202026")
    s.ff(b, 0, 0, 1, 0.035, "#c8c8cd")  # the silver trim at the bottom
    s.ff(b, 0.20, 0.12, 0.75, 0.93, "#0b0b0f")  # the big screen and its surround
    s.ff(b, 0.22, 0.17, 0.73, 0.89, "#1d2331")
    s.ff(b, 0.22, 0.60, 0.50, 0.89, "#262d3e")  # a glint
    s.fcf(b, 0.09, 0.50, 0.65, "#0b0b0f")  # the analogue nub
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):  # d-pad and face buttons
        s.fcf(b, 0.11 + dx * 0.036, 0.80 + dz * 0.12, 0.34, "#2c2c34")
        s.fcf(b, 0.88 + dx * 0.036, 0.78 + dz * 0.12, 0.34, "#2c2c34")
    for i in range(6):
        s.fcf(b, 0.20 + i * 0.07, 0.06, 0.2, "#4a4a52")
    s.ff(b, 0.80, 0.42, 0.90, 0.48, "#9a9aa2")


def xbox(s: Scene) -> None:
    b = s.box(0, 0, 0, 32.0, 26.0, 8.5, "#18181b", r=1.0, top="#202024")
    s.p_top(b, [(2, 3), (6, 3), (30, 23), (26, 23)], "#2c2c32")  # the X
    s.p_top(b, [(26, 3), (30, 3), (6, 23), (2, 23)], "#2c2c32")
    s.c_top(b, 16, 13, 3.9, "#27733a")  # the green jewel
    s.c_top(b, 16, 13, 3.0, "#3fae5a")
    s.c_top(b, 16, 13, 1.4, "#58c875")
    for i in range(12):  # the vents on the right
        s.fs(b, 0.08 + i * 0.072, 0.15, 0.08 + i * 0.072 + 0.032, 0.85, "#09090b")
    s.ff(b, 0.06, 0.62, 0.22, 0.72, "#4a4a52")
    for u in (0.30, 0.40, 0.62, 0.72):  # four controller ports
        s.ff(b, u, 0.16, u + 0.07, 0.52, "#0b0b0d")
    s.fcf(b, 0.52, 0.56, 0.5, "#d0d0d0")


def pcengine(s: Scene) -> None:
    body = s.box(0, 0, 0, 36.0, 22.0, 6.2, "#1c1c20", r=1.2, top="#222226")
    back = s.box(3.0, 0, 6.2, 31.0, 10.0, 2.2, "#202024", r=0.8, top="#26262b")
    s.ft(body, 0.62, 0.52, 0.82, 0.88, "#0b0b0d")  # the card slot
    s.fct(body, 0.72, 0.69, 1.7, "#25252a")
    for i in range(6):  # ridges at the front right
        s.ft(body, 0.85, 0.55 + i * 0.07, 0.97, 0.55 + i * 0.07 + 0.03, "#0f0f12")
    s.ft(body, 0.08, 0.60, 0.38, 0.65, "#d9702a")  # the name
    s.ff(body, 0.08, 0.30, 0.22, 0.62, "#0c0c0f")


def neogeo(s: Scene) -> None:
    body = s.box(0, 0, 0, 33.0, 22.0, 6.0, "#1c1c20", r=1.0, top="#222226")
    s.box(2.0, 0, 6.0, 29.0, 10.5, 1.2, "#202026", r=3.0, top="#27272d")
    s.ft(body, 0.16, 0.06, 0.84, 0.44, "#08080a")  # the long cartridge slot
    s.fct(body, 0.16, 0.66, 1.6, "#2a2a30")
    s.ft(body, 0.50, 0.70, 0.80, 0.77, "#d9b04a")  # the name
    s.ff(body, 0.52, 0.20, 0.74, 0.38, "#0b0b0d")  # card slots
    s.ff(body, 0.10, 0.30, 0.24, 0.55, "#0b0b0d")


def lynx(s: Scene) -> None:
    b = s.box(0, 0, 0, 27.0, 4.0, 11.0, "#5b5b62", r=4.0, top="#66666e")
    s.fcf(b, 0.14, 0.55, 2.3, "#17171b")  # the big d-pad
    s.ff(b, 0.07, 0.50, 0.21, 0.58, "#2a2a30")
    s.ff(b, 0.12, 0.30, 0.16, 0.80, "#2a2a30")
    s.ff(b, 0.35, 0.18, 0.62, 0.92, "#121216")  # screen surround
    s.ff(b, 0.38, 0.26, 0.59, 0.78, "#6f8a56")
    s.ff(b, 0.41, 0.82, 0.55, 0.88, "#d9902a")  # the name
    for i in range(3):  # option buttons
        s.ff(b, 0.66, 0.30 + i * 0.12, 0.69, 0.36 + i * 0.12, "#c9a24a")
    s.fcf(b, 0.89, 0.68, 1.0, "#17171b")  # A and B
    s.fcf(b, 0.93, 0.34, 1.0, "#17171b")
    for i in range(6):  # speaker
        s.ff(b, 0.73, 0.28 + i * 0.07, 0.83, 0.31 + i * 0.07, "#3a3a42")


def wonderswan(s: Scene) -> None:
    b = s.box(0, 0, 0, 12.1, 2.4, 7.4, "#3a5fc8", r=1.8, top="#4a70d8")
    s.ff(b, 0.28, 0.10, 0.74, 0.94, "#e4e4e8")  # the white screen surround
    s.ff(b, 0.34, 0.20, 0.68, 0.84, "#6d7a8c")
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):  # the X buttons
        s.fcf(b, 0.14 + dx * 0.065, 0.56 + dz * 0.17, 0.4, "#c9d4f2")
    s.fcf(b, 0.86, 0.34, 0.5, "#c9d4f2")
    s.fcf(b, 0.92, 0.58, 0.5, "#c9d4f2")
    s.ff(b, 0.38, 0.03, 0.50, 0.075, "#e4e4e8")
    s.ff(b, 0.55, 0.03, 0.64, 0.075, "#f28a1a")


def ngp(s: Scene) -> None:
    b = s.box(0, 0, 0, 14.5, 2.7, 8.5, "#26272d", r=2.2, top="#30313a")
    s.fcf(b, 0.12, 0.78, 0.95, "#111114")  # the stick
    s.fcf(b, 0.12, 0.78, 0.55, "#2c2c33")
    s.ff(b, 0.18, 0.08, 0.64, 0.92, "#0e0e12")  # the screen surround
    s.ff(b, 0.21, 0.16, 0.61, 0.86, "#8d8f8a")
    s.fcf(b, 0.77, 0.42, 0.8, "#101014")  # the two buttons
    s.fcf(b, 0.90, 0.58, 0.8, "#101014")
    s.ff(b, 0.70, 0.16, 0.76, 0.20, "#4a4a52")


def arcade(s: Scene) -> None:
    blue = "#2b44a6"
    low = s.box(0, 0, 0, 30.0, 34.0, 24.0, blue, r=0.6)
    s.ff(low, 0.30, 0.10, 0.70, 0.55, "#17171c")  # the coin door
    s.ff(low, 0.38, 0.30, 0.46, 0.42, "#d6322c")
    s.ff(low, 0.54, 0.30, 0.62, 0.42, "#d6322c")
    up = s.box(0, 0, 24.0, 30.0, 22.0, 28.0, blue, r=0.6)
    s.ff(up, 0.10, 0.08, 0.90, 0.80, "#101014")  # the bezel
    s.ff(up, 0.15, 0.14, 0.85, 0.74, "#168a5c")  # the screen
    s.ff(up, 0.22, 0.46, 0.30, 0.52, "#c8ffd8")  # a few invaders
    s.ff(up, 0.40, 0.46, 0.48, 0.52, "#c8ffd8")
    s.ff(up, 0.58, 0.46, 0.66, 0.52, "#c8ffd8")
    s.ff(up, 0.30, 0.30, 0.38, 0.36, "#c8ffd8")
    s.ff(up, 0.50, 0.30, 0.58, 0.36, "#c8ffd8")
    panel = s.box(0, 22.0, 21.0, 30.0, 12.0, 3.4, "#202028", r=0.5)  # the control panel
    s.box(7.0, 28.0, 24.4, 1.0, 1.0, 5.0, "#c9c9d2")  # the joystick
    s.disc(7.5, 28.5, 29.4, 2.2, 2.2, "#d6322c")
    for x, c in ((14.0, "#f2c200"), (18.5, "#35b6e8"), (23.0, "#3fae5a")):
        s.c_top(panel, x, 5.0, 1.7, c)
        s.c_top(panel, x + 1.0, 9.0, 1.7, c)
    s.box(0, 0, 52.0, 30.0, 23.0, 7.0, "#17171c", r=0.5)  # the marquee
    s.ff((0, 0, 52.0, 30.0, 23.0, 7.0), 0.06, 0.2, 0.94, 0.8, "#ffcf3a")
    s.fs((0, 0, 0, 30.0, 34.0, 24.0), 0.06, 0.40, 0.94, 0.55, "#e8318f")  # side art
    s.fs((0, 0, 0, 30.0, 34.0, 24.0), 0.06, 0.62, 0.94, 0.72, "#35d6e8")
    s.fs((0, 0, 24.0, 30.0, 22.0, 28.0), 0.06, 0.35, 0.94, 0.50, "#e8318f")
    s.fs((0, 0, 24.0, 30.0, 22.0, 28.0), 0.06, 0.58, 0.94, 0.66, "#f2c200")


def amiga(s: Scene) -> None:
    body = s.box(0, 0, 0, 47.0, 24.0, 6.0, "#cfc9b5", r=1.0, top="#d8d2be")
    for i in range(20):  # the vents across the back
        s.ft(body, 0.03 + i * 0.047, 0.04, 0.03 + i * 0.047 + 0.022, 0.20, "#a8a28d")
    s.ft(body, 0.03, 0.28, 0.97, 0.98, "#a9a38e")  # the keyboard well
    for i in range(10):  # function keys
        s.ft(body, 0.05 + i * 0.058, 0.31, 0.05 + i * 0.058 + 0.050, 0.39, "#c6c0ab")
    _keys(s, body, 4, 0.05, 0.62, 0.43, 0.12, 0.004, "#c6c0ab", 14)
    _keys(s, body, 4, 0.76, 0.96, 0.43, 0.12, 0.004, "#c6c0ab", 4)
    s.ft(body, 0.64, 0.60, 0.72, 0.72, "#c6c0ab")  # the arrow keys
    s.ft(body, 0.80, 0.14, 0.94, 0.20, "#6a6a72")  # the badge
    s.ff(body, 0.70, 0.30, 0.90, 0.40, "#25252a")  # the floppy slot


def gba(s: Scene) -> None:
    b = s.box(0, 0, 0, 14.4, 2.4, 8.2, "#5f46b8", r=2.0, top="#6e56c8")
    s.ff(b, 0.22, 0.10, 0.77, 0.93, "#14141a")  # the black screen surround
    s.ff(b, 0.28, 0.22, 0.71, 0.81, "#a0b09a")  # the screen
    s.ff(b, 0.05, 0.64, 0.17, 0.72, "#d0d0d6")  # the d-pad
    s.ff(b, 0.09, 0.52, 0.13, 0.84, "#d0d0d6")
    s.fcf(b, 0.81, 0.46, 0.58, "#cfcfd4")  # A and B
    s.fcf(b, 0.90, 0.50, 0.58, "#cfcfd4")
    s.ff(b, 0.07, 0.26, 0.13, 0.30, "#cfcfd4")  # start and select
    s.ff(b, 0.07, 0.19, 0.13, 0.23, "#cfcfd4")
    for i in range(4):  # the speaker
        s.ff(b, 0.80, 0.12 + i * 0.05, 0.93, 0.14 + i * 0.05, "#352a86")
    s.ff(b, 0.0, 0.92, 0.09, 1.0, "#cfcfd4")  # the shoulder buttons' ends
    s.ff(b, 0.91, 0.92, 1.0, 1.0, "#cfcfd4")


def virtualboy(s: Scene) -> None:
    s.beam((12.5, 5.5, 9.0), (11.0, -7.0, 0.0), 1.1, "#25252a")  # the back leg
    s.beam((12.5, 5.5, 9.0), (-2.0, 12.0, 0.0), 1.1, "#25252a")  # the front-left leg
    s.beam((12.5, 5.5, 9.0), (27.0, 8.0, 0.0), 1.1, "#25252a")  # the right leg
    s.disc(12.5, 5.5, 8.0, 1.3, 4.5, "#2c2c32")  # the neck
    s.box(1.5, 1.0, 12.0, 22.0, 10.0, 1.6, "#18181c", r=2.5)
    v = s.box(0, 0, 13.0, 25.0, 12.0, 8.0, "#d6322c", r=3.2, top="#e24038")
    s.ff(v, 0.14, 0.05, 0.86, 0.50, "#18181c")  # the eyepiece
    s.ff(v, 0.20, 0.62, 0.42, 0.78, "#f4c4c0")  # its label


def nds(s: Scene) -> None:
    low = s.box(0, 6.0, 0, 14.8, 8.4, 1.4, "#2f55d8", r=1.0, top="#3a62e6")
    s.box(0, 5.0, 0, 14.8, 1.4, 1.8, "#1d3aa0")  # the hinge
    lid = s.tilted((0, 5.4, 1.4), (14.8, 0, 0), (0, 0.85, 0.31), (0, -2.9, 7.9), "#2f55d8")
    s.d_on(lid, 4.0, 1.4, 10.8, 6.7, "#101014")  # the upper screen
    s.d_on(lid, 4.5, 1.9, 10.3, 6.2, "#2c2f36")
    for i in range(4):  # speaker dots on either side
        s.d_on(lid, 1.3 + i * 0.5, 2.8, 1.6 + i * 0.5, 5.6, "#1d3aa0")
        s.d_on(lid, 12.2 + i * 0.5, 2.8, 12.5 + i * 0.5, 5.6, "#1d3aa0")
    s.d_top(low, 4.0, 0.8, 10.8, 6.0, "#101014")  # the lower screen
    s.d_top(low, 4.5, 1.2, 10.3, 5.6, "#2c2f36")
    s.d_top(low, 1.2, 3.8, 3.2, 4.5, "#17171c")  # the d-pad
    s.d_top(low, 1.9, 3.1, 2.6, 5.2, "#17171c")
    for x, y in ((12.7, 2.8), (12.7, 4.8), (11.7, 3.8), (13.7, 3.8)):  # the four face buttons
        s.c_top(low, x, y, 0.5, "#cfd4e6")
    s.d_top(low, 11.9, 6.3, 13.5, 6.7, "#cfd4e6")


def n3ds(s: Scene) -> None:
    low = s.box(0, 6.0, 0, 13.4, 7.4, 1.2, "#1da8c8", r=1.0, top="#2cbadc")
    s.box(0, 5.0, 0, 13.4, 1.4, 1.6, "#15788f")
    lid = s.tilted((0, 5.4, 1.2), (13.4, 0, 0), (0, 0.85, 0.31), (0, -2.9, 7.9), "#17171c")
    s.d_on(lid, 2.4, 1.2, 11.0, 7.0, "#0c0c10")  # the wide upper screen
    s.d_on(lid, 2.8, 1.6, 10.6, 6.6, "#cfd3d8")
    s.d_on(lid, 6.5, 7.3, 6.9, 7.65, "#3a3a44")  # the camera
    s.d_top(low, 4.3, 0.7, 9.3, 5.6, "#101014")  # the lower screen
    s.d_top(low, 4.7, 1.1, 8.9, 5.2, "#cfd3d8")
    s.c_top(low, 2.2, 2.4, 1.0, "#c7ccd2")  # the circle pad
    s.d_top(low, 1.2, 5.3, 3.4, 5.9, "#cfe9f0")  # the d-pad
    s.d_top(low, 1.9, 4.6, 2.7, 6.6, "#cfe9f0")
    for x, y in ((11.4, 2.6), (11.4, 4.4), (10.5, 3.5), (12.3, 3.5)):
        s.c_top(low, x, y, 0.45, "#e8f2f6")
    s.d_top(low, 4.6, 6.4, 5.6, 6.8, "#cfe9f0")
    s.d_top(low, 6.3, 6.4, 7.3, 6.8, "#cfe9f0")
    s.d_top(low, 8.0, 6.4, 9.0, 6.8, "#cfe9f0")


def segacd(s: Scene) -> None:
    low = s.box(0, 0, 0, 31.0, 26.0, 6.5, "#1d1d22", r=0.8, top="#242429")
    s.ff(low, 0.05, 0.50, 0.30, 0.78, "#d8d8e0")  # SEGA CD
    s.ff(low, 0.34, 0.26, 0.76, 0.52, "#08080a")  # the disc tray
    s.ff(low, 0.80, 0.30, 0.94, 0.46, "#33333a")
    s.box(31.0, 1.5, 0.0, 2.8, 21.0, 13.0, "#17171b", r=0.6)  # the arm the Genesis plugs into
    s.at(1.5, 4.5, 6.5)
    genesis(s)
    s.at(0, 0, 0)


def switch(s: Scene) -> None:
    t = s.box(3.9, 0, 0, 16.4, 1.4, 10.2, "#18181c", r=0.5)
    s.ff(t, 0.03, 0.04, 0.97, 0.96, "#101216")
    s.ff(t, 0.05, 0.07, 0.95, 0.93, "#2b313b")  # the screen
    left = s.box(0, 0, 0, 4.1, 1.6, 10.2, "#1fb5e8", r=1.4)
    right = s.box(20.1, 0, 0, 4.1, 1.6, 10.2, "#f23b3b", r=1.4)
    s.fcf(left, 0.52, 0.78, 1.0, "#2a2a30")  # left stick
    s.fcf(left, 0.52, 0.78, 0.6, "#40404a")
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):  # the four arrow buttons
        s.fcf(left, 0.52 + dx * 0.20, 0.50 + dz * 0.11, 0.3, "#1a1a20")
    s.ff(left, 0.38, 0.93, 0.66, 0.96, "#1a1a20")  # minus
    s.ff(left, 0.38, 0.12, 0.66, 0.24, "#1a1a20")  # the screenshot button
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):  # A, B, X, Y
        s.fcf(right, 0.48 + dx * 0.20, 0.72 + dz * 0.11, 0.3, "#1a1a20")
    s.fcf(right, 0.48, 0.30, 1.0, "#2a2a30")  # right stick
    s.fcf(right, 0.48, 0.30, 0.6, "#40404a")
    s.fcf(right, 0.48, 0.10, 0.4, "#1a1a20")  # home


def wii(s: Scene) -> None:
    s.box(-1.2, -1.2, 0, 17.9, 7.0, 2.4, "#7e7e83", r=0.8, top="#9a9aa0")  # the stand
    b = s.box(0, 0, 2.4, 15.5, 4.4, 21.5, "#f2f2f5", r=0.6)
    s.ff(b, 0.13, 0.12, 0.17, 0.90, "#14141a")  # the disc slot
    s.ff(b, 0.04, 0.90, 0.09, 0.93, "#35b6e8")
    s.ff(b, 0.04, 0.86, 0.09, 0.885, "#9cd9f0")
    s.ff(b, 0.06, 0.04, 0.20, 0.08, "#bdbdc4")
    s.ft(b, 0.10, 0.50, 0.90, 0.54, "#dcdce2")


def wiiu(s: Scene) -> None:
    con = s.box(11.0, 0, 0, 26.9, 17.2, 4.6, "#eeeef2", r=1.8, top="#f6f6fa")
    s.ff(con, 0.48, 0.52, 0.92, 0.58, "#15151a")  # the disc slot
    s.ff(con, 0.48, 0.40, 0.92, 0.46, "#cfcfd6")
    s.fcf(con, 0.40, 0.50, 0.35, "#d63a34")
    pad = s.box(0, 18.5, 0, 25.6, 2.2, 13.5, "#f4f4f7", r=1.8)  # the GamePad, in front
    s.ff(pad, 0.27, 0.88, 0.73, 0.95, "#16161a")
    s.ff(pad, 0.19, 0.16, 0.79, 0.80, "#08080b")  # its screen
    s.fcf(pad, 0.09, 0.72, 1.2, "#e8e8ee")
    s.fcf(pad, 0.91, 0.72, 1.2, "#e8e8ee")
    s.ff(pad, 0.06, 0.44, 0.14, 0.48, "#c0c0c8")  # d-pad
    s.ff(pad, 0.09, 0.36, 0.11, 0.56, "#c0c0c8")
    for dx, dz in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        s.fcf(pad, 0.88 + dx * 0.035, 0.46 + dz * 0.07, 0.3, "#d2d2d8")
    s.fcf(pad, 0.50, 0.07, 0.5, "#d0d0d6")


def ps3(s: Scene) -> None:
    b = s.box(0, 0, 0, 29.0, 29.0, 6.5, "#1b1b1f", r=2.2, top="#25252a")
    s.ff(b, 0.10, 0.18, 0.92, 0.28, "#bdbdc4")  # the disc slot
    s.ft(b, 0.70, 0.10, 0.90, 0.16, "#6a6a72")  # the logo
    s.ft(b, 0.12, 0.84, 0.18, 0.90, "#3a3a42")  # power and eject
    s.ft(b, 0.22, 0.84, 0.28, 0.90, "#3a3a42")


MODELS = {"nes": nes, "gb": gb, "gbc": gbc, "sms": sms, "atari2600": atari2600, "atari7800": atari7800, "gamegear": gamegear, "msx": msx, "snes": snes, "genesis": genesis, "segacd": segacd, "pcengine": pcengine, "neogeo": neogeo, "amiga": amiga, "lynx": lynx, "wonderswan": wonderswan, "ngp": ngp, "arcade": arcade, "psx": psx, "saturn": saturn, "gba": gba, "virtualboy": virtualboy, "nds": nds, "psp": psp, "n64": n64, "dreamcast": dreamcast, "gc": gc, "ps2": ps2, "xbox": xbox, "wii": wii, "wiiu": wiiu, "ps3": ps3, "switch": switch, "n3ds": n3ds}

ERA = {cid: era_of(cid) for cid in MODELS}
