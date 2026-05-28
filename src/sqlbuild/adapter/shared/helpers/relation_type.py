"""Helpers for adapter relation type metadata."""

from __future__ import annotations

from sqlbuild.adapter.shared.types import RelationType


def normalize_relation_type(value: str) -> RelationType:
    """Normalize warehouse relation type strings into framework categories."""

    normalized: str = value.strip().lower().replace("_", " ")
    if normalized in {"base table", "table", "managed", "external"}:
        return RelationType.TABLE
    if normalized in {"view", "base view"}:
        return RelationType.VIEW
    return RelationType.OTHER
