"""Source freshness type declarations."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class SourceFreshnessComparableRecord(Protocol):
    @property
    def data_version_hash(self) -> str: ...

    @property
    def value_kind(self) -> str: ...

    @property
    def data_version(self) -> str | None: ...


class SourceFreshnessAgeStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    ERROR = "error"
    UNKNOWN = "unknown"


class SourceFreshnessUnknownReason(StrEnum):
    """Why one source's freshness could not be observed."""

    UNAVAILABLE = "unavailable"
    ERROR = "error"
    NO_FRESHNESS_CONFIG = "no_freshness_config"
