"""Runtime SQL relation maps for Python node contexts and hard-coded name guards."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.references.main.render_source_relation import render_source_relation
from sqlbuild.errors.contracts.exceptions import SharedInputError
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_python_relation_targets_impl(
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


def build_project_relation_targets_impl(
    *, adapter: BaseAdapter, plan_output: PlanOutput
) -> dict[SqlResourceRef, str] | None:
    """Return every planned project relation for hard-coded name warnings, or None when off."""

    if not plan_output.enforce_explicit_references:
        return None
    return {
        ref: relation
        for ref in _planned_relation_refs(plan_output=plan_output)
        if (relation := _planned_relation(adapter=adapter, plan_output=plan_output, ref=ref))
        is not None
    }


def _planned_relation_refs(*, plan_output: PlanOutput) -> frozenset[SqlResourceRef]:
    refs: set[SqlResourceRef] = {
        SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=name)
        for name in plan_output.model_locations
    }
    refs.update(
        SqlResourceRef(kind=SqlResourceRefKind.SEED, name=name)
        for name in plan_output.seed_locations
    )
    source_name: str
    for source_name in plan_output.python_source_entries:
        refs.add(SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source_name))
    return frozenset(refs)


def _resolve_relation(
    *,
    adapter: BaseAdapter,
    project: CompiledProject,
    plan_output: PlanOutput,
    ref: SqlResourceRef,
) -> str:
    planned: str | None = _planned_relation(adapter=adapter, plan_output=plan_output, ref=ref)
    if planned is not None:
        return planned
    if ref.kind == SqlResourceRefKind.SOURCE:
        raise SharedInputError(
            f"Python node source '{ref.name}' is missing from the resolved plan source map"
        )
    location: CompiledRelationLocation | None = next(
        (
            resource.destination
            for resource in (
                project.models if ref.kind == SqlResourceRefKind.MODEL else project.seeds
            )
            if resource.name == ref.name
        ),
        None,
    )
    if location is None:
        raise SharedInputError(f"Python node references unknown {ref.kind.value} '{ref.name}'")
    return resolve_relation_location_qualified_name(adapter=adapter, location=location)


def _planned_relation(
    *, adapter: BaseAdapter, plan_output: PlanOutput, ref: SqlResourceRef
) -> str | None:
    if ref.kind == SqlResourceRefKind.SOURCE:
        planned_sources: dict[str, SourceEntry] = plan_output.python_source_entries
        planned_source: SourceEntry | None = planned_sources.get(ref.name)
        if planned_source is None:
            return None
        return render_source_relation(entry=planned_source, adapter=adapter)
    locations: dict[str, CompiledRelationLocation] = (
        plan_output.model_locations
        if ref.kind == SqlResourceRefKind.MODEL
        else plan_output.seed_locations
    )
    location: CompiledRelationLocation | None = locations.get(ref.name)
    if location is None:
        return None
    return resolve_relation_location_qualified_name(adapter=adapter, location=location)
