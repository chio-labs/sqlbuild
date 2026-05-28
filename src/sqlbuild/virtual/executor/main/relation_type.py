"""Public virtual relation type helpers."""

from __future__ import annotations

from sqlbuild.virtual.executor.helpers.rewrite import relation_type_for_model


def resolve_model_relation_type(materialized: str | None) -> str:
    """Return the persisted physical relation type for a model materialization."""

    return relation_type_for_model(materialized)
