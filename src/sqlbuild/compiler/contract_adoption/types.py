"""Contract adoption type-layer declarations."""

from __future__ import annotations

from enum import StrEnum


class ContractAction(StrEnum):
    """Supported contract command actions."""

    DIFF = "diff"
    GENERATE = "generate"


class ContractFindingKind(StrEnum):
    """Stable physical-to-authored contract difference categories."""

    MISSING_DECLARATION = "missing_declaration"
    MISSING_PHYSICAL_COLUMN = "missing_physical_column"
    TYPE_MISMATCH = "type_mismatch"
    RELATION_MISSING = "relation_missing"
    INSPECTION_UNAVAILABLE = "inspection_unavailable"
    OWNERSHIP_CONFLICT = "ownership_conflict"
