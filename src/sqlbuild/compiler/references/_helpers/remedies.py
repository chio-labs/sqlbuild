"""Remedies for project relation names hard-coded in Python SQL."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def hard_coded_relation_remedy_impl(
    *,
    owner_kind: HardCodedRelationOwnerKind,
    ref: SqlResourceRef,
    upstream_loader_by_source: Mapping[str, str],
) -> str:
    """Return how the owner should read ``ref`` instead of naming it in SQL."""

    typed: str = f'{ref.kind.value}("{ref.name}")'
    if owner_kind is HardCodedRelationOwnerKind.LOADER:
        if ref.kind is not SqlResourceRefKind.SOURCE:
            return (
                "loaders run before models and seeds and cannot read them; read "
                f"{ref.kind.value}:{ref.name} from a task or asset instead"
            )
        loader_name: str | None = upstream_loader_by_source.get(ref.name)
        if loader_name is not None:
            return f"use ctx.loader({loader_name}) instead of the relation name"
        return f'use ctx.source("{ref.name}") instead of the relation name'
    declaration: str = (
        f"@hook(reads={typed})"
        if owner_kind is HardCodedRelationOwnerKind.HOOK
        else f"depends_on={typed}"
    )
    return (
        f"declare it with {declaration} and use ctx.relation({typed}) instead of the relation name"
    )
