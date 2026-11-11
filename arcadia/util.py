from __future__ import annotations

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
