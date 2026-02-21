from __future__ import annotations

from datetime import UTC, datetime


def utc_from_datetime_iso(dt: datetime) -> str:
    """Normalize a datetime to lexicographically sortable UTC timestamp."""
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso() -> str:
    """Return a lexicographically sortable UTC timestamp."""
    return utc_from_datetime_iso(datetime.now(UTC))
