"""Runtime SQL relation maps for Python node contexts."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationTarget
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.shared.types import SqlResourceRefKind
from sqlbuild.spec.models.source import SourceEntry


def build_python_relation_targets(
    *, adapter: BaseAdapter, project: CompiledProject, plan_output: PlanOutput
) -> dict[SqlResourceRef, str]:
    """Return adapter-qualified runtime relation strings for model/source refs."""

    targets: dict[SqlResourceRef, str] = {}
    model_name: str
    target: CompiledRelationTarget
    for model_name, target in plan_output.model_targets.items():
        targets[SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model_name)] = (
            resolve_target_qualified_name(adapter=adapter, target=target)
        )
    for source in project.sources:
        targets[SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source.name)] = (
            _source_relation(adapter=adapter, source_name=source.name, plan_output=plan_output)
        )
    return targets


def _source_relation(*, adapter: BaseAdapter, source_name: str, plan_output: PlanOutput) -> str:
    source_entry: SourceEntry = (plan_output.source_read_map or plan_output.source_map)[source_name]
    return render_source_relation(source_entry, adapter=adapter)
