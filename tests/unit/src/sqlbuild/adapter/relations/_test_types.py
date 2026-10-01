from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataSqlOwnershipTestCase:
    """Source modules allowed to contain warehouse catalog SQL."""

    description: str
    allowed_modules: frozenset[str]
    expected_unlisted_modules: tuple[str, ...]
