"""Runtime node result type declarations."""

from __future__ import annotations

from enum import StrEnum


class NodeResultStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARN = "warn"
