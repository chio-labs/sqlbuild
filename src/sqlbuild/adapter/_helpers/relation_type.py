"""Public relation type normalization capability."""

from __future__ import annotations

from sqlbuild.adapter.constants import TABLE_RELATION_TYPE_NAMES, VIEW_RELATION_TYPE_NAMES
from sqlbuild.adapter.types import RelationType


def normalize_relation_type(value: str) -> RelationType:
    """Normalize warehouse relation type strings into framework categories."""

    normalized: str = value.strip().lower().replace("_", " ")
    if normalized in TABLE_RELATION_TYPE_NAMES:
        return RelationType.TABLE
    if normalized in VIEW_RELATION_TYPE_NAMES:
        return RelationType.VIEW
    return RelationType.OTHER
