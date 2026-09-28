"""Source relation rendering entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.compiler.references._helpers.source_relations import render_source_relation_impl
from sqlbuild.spec.contracts.models import SourceEntry


def render_source_relation(*, entry: SourceEntry, adapter: StrictAdapter | None = None) -> str:
    """Render a source as a SQL table factor."""

    return render_source_relation_impl(entry=entry, adapter=adapter)
