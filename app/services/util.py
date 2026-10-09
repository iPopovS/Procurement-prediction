"""Small parsing helpers shared by services (no third-party deps)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 string/datetime into a *naive UTC* datetime, or None.

    GosPlan returns naive strings such as ``2026-01-30T00:03:03.391000``; these are kept
    as-is (the model's ``published_at_ts`` convention is UTC-naive, see README section 6).
    Strings that carry an offset are converted to UTC first.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def to_float(value: Any) -> float | None:
    """Best-effort float conversion; returns None for None/''/NaN/inf/garbage."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
            if value == "":
                return None
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def str_list(value: Any) -> list[str]:
    """Normalise a JSON list of codes to a list of non-empty strings."""
    if not isinstance(value, (list, tuple)):
        return []
    return [str(x) for x in value if x is not None and str(x) != ""]


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None
