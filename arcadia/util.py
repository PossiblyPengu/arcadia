from __future__ import annotations

from collections import Counter
from datetime import datetime


def fmt_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def fmt_clock(seconds: int) -> str:
    """Running-timer style: 03:07 or 1:02:03."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def fmt_timestamp(ts: float | None) -> str:
    if not ts:
        return "never"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def snapshot_label(name: str) -> str:
    """'20260102-130455-123456-auto-before-restore' -> '2026-01-02 13:04:55 (auto-before-restore)'."""
    parts = name.split("-", 3)
    if len(parts) < 3:
        return name
    try:
        when = datetime.strptime(parts[0] + parts[1], "%Y%m%d%H%M%S")
    except ValueError:
        return name
    label = f" ({parts[3]})" if len(parts) > 3 and parts[3] else ""
    return when.strftime("%Y-%m-%d %H:%M:%S") + label


def fmt_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def bundle_summary(kinds: list[str], update_versions: list[str] | None = None) -> str:
    """'3 discs' / '1 update (v131072), 2 DLC' for the files attached to a game."""
    counts = Counter(kinds)
    bits = []
    if counts["disc"]:
        bits.append(f"{counts['disc']} disc{'s' if counts['disc'] != 1 else ''}")
    if counts["update"]:
        text = f"{counts['update']} update{'s' if counts['update'] != 1 else ''}"
        versions = [v for v in (update_versions or []) if v]
        if versions:
            newest = max(versions, key=lambda v: [int(x) for x in v.lstrip("v").split(".") if x.isdigit()] or [0])
            text += f" (latest {newest})"
        bits.append(text)
    if counts["dlc"]:
        bits.append(f"{counts['dlc']} DLC")
    return ", ".join(bits)
