"""Runtime SQL relation maps for Python node contexts."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.references.main._render_source_relation import render_source_relation
from sqlbuild.errors.contracts.exceptions import SharedInputError
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_python_relation_targets(
    *,
    adapter: BaseAdapter,
    project: CompiledProject,
    plan_output: PlanOutput,
    required_refs: frozenset[SqlResourceRef] | None = None,
) -> dict[SqlResourceRef, str]:
    """Return adapter-qualified runtime relations required by selected Python nodes."""

    targets: dict[SqlResourceRef, str] = {}
    refs: frozenset[SqlResourceRef] = (
        required_refs
        if required_refs is not None
        else _planned_relation_refs(plan_output=plan_output)
    )
    ref: SqlResourceRef
    for ref in refs:
        targets[ref] = _resolve_relation(
            adapter=adapter,
            project=project,
            plan_output=plan_output,
            ref=ref,
        )
    return targets


def _planned_relation_refs(*, plan_output: PlanOutput) -> frozenset[SqlResourceRef]:
    refs: set[SqlResourceRef] = {
        SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=name)
        for name in plan_output.model_locations
    }
    source_name: str
    for source_name in (plan_output.source_read_map or plan_output.source_map):
        refs.add(SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source_name))
    return frozenset(refs)


def _resolve_relation(
    *,
    adapter: BaseAdapter,
    project: CompiledProject,
    plan_output: PlanOutput,
    ref: SqlResourceRef,
) -> str:
    if ref.kind == SqlResourceRefKind.MODEL:
        planned_model: CompiledRelationLocation | None = plan_output.model_locations.get(ref.name)
        if planned_model is not None:
            return resolve_relation_location_qualified_name(
                adapter=adapter, location=planned_model
            )
        model: CompiledModel
        for model in project.models:
            if model.name == ref.name:
                return resolve_relation_location_qualified_name(
                    adapter=adapter, location=model.destination
                )
        raise SharedInputError(f"Python node references unknown model '{ref.name}'")
    planned_sources: dict[str, SourceEntry] = plan_output.source_read_map or plan_output.source_map
    planned_source: SourceEntry | None = planned_sources.get(ref.name)
    if planned_source is not None:
        return render_source_relation(entry=planned_source, adapter=adapter)
    raise SharedInputError(
        f"Python node source '{ref.name}' is missing from the resolved plan source map"
    )
