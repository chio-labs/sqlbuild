"""State event helper functions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def backup_id() -> str:
    """Return a portable backup id safe for schema names."""

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def event_id() -> str:
    """Return a unique migration event id."""

    return uuid4().hex
