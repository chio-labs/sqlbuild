"""Runtime SQL relation maps for Python node contexts."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relation_naming.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.references.main.render_source_relation import render_source_relation
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_python_relation_targets(
    *, adapter: BaseAdapter, project: CompiledProject, plan_output: PlanOutput
) -> dict[SqlResourceRef, str]:
    """Return adapter-qualified runtime relation strings for model/source refs."""

    targets: dict[SqlResourceRef, str] = {}
    model_name: str
    target: CompiledRelationLocation
    for model_name, target in plan_output.model_locations.items():
        targets[SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model_name)] = (
            resolve_relation_location_qualified_name(adapter=adapter, location=target)
        )
    for source in project.sources:
        targets[SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source.name)] = (
            _source_relation(adapter=adapter, source_name=source.name, plan_output=plan_output)
        )
    return targets


def _source_relation(*, adapter: BaseAdapter, source_name: str, plan_output: PlanOutput) -> str:
    source_entry: SourceEntry = (plan_output.source_read_map or plan_output.source_map)[source_name]
    return render_source_relation(entry=source_entry, adapter=adapter)
