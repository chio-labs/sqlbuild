"""Debug command helper types."""

from __future__ import annotations

from enum import StrEnum


class DebugCheckStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    SKIP = "SKIP"
