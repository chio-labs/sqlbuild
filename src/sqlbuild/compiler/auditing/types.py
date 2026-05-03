"""Auditing domain types."""

from __future__ import annotations

from enum import StrEnum


class AuditSeverity(StrEnum):
    WARN = "warn"
    ERROR = "error"


class AuditRunScope(StrEnum):
    FINAL = "final"
    DELTA_AND_FINAL = "delta_and_final"


class AuditAttachmentKind(StrEnum):
    SOURCE = "source"
    MODEL = "model"
    END = "end"


class AuditOutcome(StrEnum):
    PASS = "pass"
    WARN = "warn"
    ERROR = "error"
