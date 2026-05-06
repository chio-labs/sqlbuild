"""Compiler diagnostic types."""

from __future__ import annotations

from enum import StrEnum


class DiagnosticPhase(StrEnum):
    """Phase that produced a compiler diagnostic."""

    COMPILE = "compile"
    CONTRACT = "contract"
    PLAN = "plan"
    BUILD = "build"
    AUDIT = "audit"
    TEST = "test"
    CONNECTION = "connection"


class DiagnosticSeverity(StrEnum):
    """Severity for a compiler diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
