#!/usr/bin/env python3
"""A tiny original NES program for testing Arcadia: the screen slowly cycles through colours.

NROM (mapper 0), 16 KB of program at $C000, 8 KB of blank pattern table. Rendering stays off, so the PPU shows the
backdrop colour ($3F00), which the program changes every 16 frames during vblank.

    make_test_rom.py OUT.nes
"""
import sys

ORG = 0xC000
code = bytearray()
labels: dict[str, int] = {}
fixups: list[tuple[int, str, str]] = []  # (where, label, kind: "rel" or "abs")


def at() -> int:
    return ORG + len(code)


def label(name: str) -> None:
    labels[name] = at()


def emit(*bs: int) -> None:
    code.extend(bs)


def branch(op: int, name: str) -> None:
    emit(op, 0)
    fixups.append((len(code) - 1, name, "rel"))


def jmp(name: str) -> None:
    emit(0x4C, 0, 0)
    fixups.append((len(code) - 2, name, "abs"))


def wait_vblank(name: str) -> None:
    label(name)
    emit(0x2C, 0x02, 0x20)  # BIT $2002
    branch(0x10, name)      # BPL name


label("reset")
emit(0x78, 0xD8)                    # SEI, CLD
emit(0xA2, 0x40, 0x8E, 0x17, 0x40)  # LDX #$40, STX $4017 (no APU frame IRQ)
emit(0xA2, 0xFF, 0x9A, 0xE8)        # LDX #$FF, TXS, INX (X = 0)
emit(0x8E, 0x00, 0x20)              # STX $2000 (no NMI)
emit(0x8E, 0x01, 0x20)              # STX $2001 (rendering off)
emit(0x8E, 0x10, 0x40)              # STX $4010 (no DMC IRQ)
wait_vblank("warm1")                # the PPU needs two vblanks to warm up
wait_vblank("warm2")
emit(0x86, 0x00)                    # STX $00 (frame counter = 0)
label("loop")
wait_vblank("frame")
emit(0xE6, 0x00, 0xA5, 0x00)        # INC $00, LDA $00
emit(0x4A, 0x4A, 0x4A, 0x4A)        # LSR x4: changes every 16 frames
emit(0x29, 0x07, 0x09, 0x21)        # AND #$07, ORA #$21: bright blue … yellow ($21-$28)
emit(0xA2, 0x3F, 0x8E, 0x06, 0x20)  # LDX #$3F, STX $2006
emit(0xA2, 0x00, 0x8E, 0x06, 0x20)  # LDX #$00, STX $2006
emit(0x8D, 0x07, 0x20)              # STA $2007: the backdrop colour
emit(0x8E, 0x06, 0x20, 0x8E, 0x06, 0x20)  # STX $2006 twice: address back to $0000 (shows the backdrop)
jmp("loop")
label("irq")
emit(0x40)                          # RTI (for NMI and IRQ, which stay off)

for where, name, kind in fixups:
    target = labels[name]
    if kind == "rel":
        offset = target - (ORG + where + 1)
        assert -128 <= offset <= 127, name
        code[where] = offset & 0xFF
    else:
        code[where:where + 2] = target.to_bytes(2, "little")

prg = bytearray(code) + bytes(0x4000 - len(code))
prg[0x3FFA:0x4000] = (labels["irq"].to_bytes(2, "little") + labels["reset"].to_bytes(2, "little")
                      + labels["irq"].to_bytes(2, "little"))
header = b"NES\x1a" + bytes([1, 1, 0, 0]) + bytes(8)  # 1 x 16 KB PRG, 1 x 8 KB CHR, mapper 0, horizontal
rom = header + bytes(prg) + bytes(0x2000)
with open(sys.argv[1], "wb") as f:
    f.write(rom)
print(f"{sys.argv[1]}: {len(rom)} bytes, {len(code)} bytes of code")
