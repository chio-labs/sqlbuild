"""Shared source freshness type declarations."""

from __future__ import annotations

from typing import Protocol


class SourceFreshnessComparableRecord(Protocol):
    """Record shape shared by direct and virtual source freshness state."""

    @property
    def value_kind(self) -> str:
        """Source freshness value kind."""

    @property
    def data_version(self) -> str | None:
        """Normalized source freshness data version."""

    @property
    def data_version_hash(self) -> str:
        """Hash of the normalized data version."""
