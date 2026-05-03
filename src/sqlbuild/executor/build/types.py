"""Build executor domain types."""

from __future__ import annotations

from enum import StrEnum


class BuildStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
