"""Test case types for the compile reuse import footprint."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReuseImportFootprintTestCase:
    """Modules a full compile loads and a reused compile must leave unloaded."""

    description: str
    checked_modules: tuple[str, ...]
    expected_full_loaded: tuple[str, ...]
    expected_reused_loaded: tuple[str, ...]
