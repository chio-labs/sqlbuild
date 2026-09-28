"""Hard-coded project relation remedy entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.references._helpers.remedies import hard_coded_relation_remedy_impl
from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.models import SqlResourceRef


def hard_coded_relation_remedy(
    *,
    owner_kind: HardCodedRelationOwnerKind,
    ref: SqlResourceRef,
    upstream_loader_by_source: Mapping[str, str] | None = None,
) -> str:
    """Return how Python code should read ``ref`` instead of naming it in SQL."""

    return hard_coded_relation_remedy_impl(
        owner_kind=owner_kind,
        ref=ref,
        upstream_loader_by_source={}
        if upstream_loader_by_source is None
        else upstream_loader_by_source,
    )
