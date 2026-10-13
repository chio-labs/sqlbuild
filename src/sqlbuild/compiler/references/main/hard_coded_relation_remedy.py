"""Hard-coded project relation remedy entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.models import SqlResourceRef


def hard_coded_relation_remedy(
    *,
    owner_kind: HardCodedRelationOwnerKind,
    ref: SqlResourceRef,
    upstream_loader_by_source: Mapping[str, str] | None = None,
) -> str:
    """Return how Python code should read ``ref`` instead of naming it in SQL."""

    return _native.hard_coded_relation_remedy(
        owner_kind.value,
        (ref.kind.value, ref.name),
        list((upstream_loader_by_source or {}).items()),
    )
