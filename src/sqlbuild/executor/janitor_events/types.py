"""Janitor audit event type declarations."""

from __future__ import annotations

from enum import StrEnum


class JanitorEventType(StrEnum):
    """Physical janitor actions recorded in the audit table."""

    ARCHIVE = "archive"
    DELETE = "delete"
