"""Utility helpers — time/format functions."""

import datetime as dt


def format_mmss(seconds: int | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS string."""
    if seconds is None or seconds < 0:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def iso_datetime_from_ts(ts: float) -> str:
    """Convert a UNIX timestamp to a human-readable ISO datetime string."""
    try:
        return dt.datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")
    except Exception:
        return ""
