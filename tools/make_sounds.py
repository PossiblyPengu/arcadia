#!/usr/bin/env python3
"""Generate the small sound effects in arcadia/assets/sounds (plain WAV files, no samples from anywhere)."""

import math
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "arcadia" / "assets" / "sounds"


def tone(notes, volume=0.5):
    """notes: (frequency Hz, milliseconds, glide-to Hz or None). Each fades in and out so there are no clicks."""
    samples = []
    for freq, ms, glide in notes:
        n = int(RATE * ms / 1000)
        phase = 0.0
        for i in range(n):
            f = freq + ((glide - freq) * i / n if glide else 0)
            phase += 2 * math.pi * f / RATE
            envelope = min(1.0, i / (RATE * 0.003)) * math.exp(-3.2 * i / n) * min(1.0, (n - i) / (RATE * 0.004))
            samples.append(volume * envelope * (math.sin(phase) + 0.25 * math.sin(2 * phase)) / 1.25)
    return samples


def write(name, samples):
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))


if __name__ == "__main__":
    write("tick", tone([(1500, 28, 900)], 0.45))
    write("open", tone([(660, 70, None), (990, 130, 1100)], 0.5))
    write("back", tone([(740, 60, None), (520, 110, 440)], 0.45))
    print("sounds written to", OUT)
