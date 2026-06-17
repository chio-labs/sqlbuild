"""dbt dependency baseline planning helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.planner.models import DependencyBaselinePlanEntry, RelationReusePlan
from sqlbuild.compiler.planner.types import RelationReuseKind
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtInteropPlan,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    find_direct_dbt_dependency_unique_ids,
)
from sqlbuild.integrations.dbt.types import DbtReusePlanAction


def dependency_baseline_unique_ids(
    *, project: CompiledProject, manifest: DbtManifestIndex, plan: DbtInteropPlan
) -> tuple[str, ...]:
    """Return direct dbt dependencies not explicitly selected as dbt work."""

    explicit_unique_ids: frozenset[str] = frozenset(
        (
            *plan.dbt_selected_unique_ids,
            *plan.selection.dbt_required_unique_ids,
            *(
                unique_id
                for unique_ids in plan.selection.dbt_anchor_unique_ids_by_term.values()
                for unique_id in unique_ids
            ),
        )
    )
    return tuple(
        unique_id
        for unique_id in find_direct_dbt_dependency_unique_ids(
            project=project,
            manifest=manifest,
            selected_model_names=plan.selection.sqlbuild_model_names,
        )
        if unique_id not in explicit_unique_ids
    )


def build_dbt_native_dependency_baseline_entries(
    *, plan: DbtReusePlanningResult | None, destination_target_name: str | None
) -> tuple[DependencyBaselinePlanEntry, ...]:
    """Convert dbt dependency baseline reuse entries to native baseline entries."""

    if plan is None:
        return ()
    entries: list[DependencyBaselinePlanEntry] = []
    entry: DbtReusePlanEntry
    for entry in plan.entries:
        if entry.action not in {DbtReusePlanAction.COMPLETE_REUSE, DbtReusePlanAction.SEEDED_REUSE}:
            continue
        if entry.destination_relation_name is None or entry.origin_relation_name is None:
            continue
        destination_database, destination_schema, destination_name = _relation_parts(
            relation_name=entry.destination_relation_name
        )
        origin_database, origin_schema, origin_name = _relation_parts(
            relation_name=entry.origin_relation_name
        )
        entries.append(
            DependencyBaselinePlanEntry(
                name=entry.unique_id,
                destination=CompiledRelationLocation(
                    database=destination_database,
                    schema=destination_schema,
                    name=destination_name,
                    qualified_name=entry.destination_relation_name,
                ),
                relation_reuse=RelationReusePlan(
                    kind=RelationReuseKind.COMPLETE_RELATION_REUSE,
                    origin=CompiledRelationLocation(
                        database=origin_database,
                        schema=origin_schema,
                        name=origin_name,
                        qualified_name=entry.origin_relation_name,
                    ),
                    reuse_from_target_name="dbt",
                    hard_copy=True,
                    fingerprint_database=None,
                    fingerprint_schema="",
                    destination_target_name=destination_target_name,
                ),
                fingerprint_version_hash=None,
                resource_label=entry.materialization or "dbt",
            )
        )
    return tuple(entries)


def _relation_parts(*, relation_name: str) -> tuple[str | None, str | None, str]:
    parts: list[str] = [_unquote_relation_part(part=part) for part in relation_name.split(".")]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return None, None, parts[0]


def _unquote_relation_part(*, part: str) -> str:
    return part.strip().strip('"').strip("`").removeprefix("[").removesuffix("]")
