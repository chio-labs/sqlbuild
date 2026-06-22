"""dbt reuse_from planning pipeline helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.exceptions import DbtReuseUnavailableError
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.reuse_candidates import (
    build_dbt_reuse_planning_result,
    mark_missing_dbt_reuse_origin_relations,
    resolve_dbt_reuse_candidates,
    resolve_dbt_reuse_candidates_for_plan,
)
from sqlbuild.integrations.dbt.helpers.reuse_from import compile_reuse_from_manifest
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtInteropPlan,
    DbtModelPlanningResult,
    DbtReuseCandidateResolution,
    DbtReuseFromCompileResult,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.spec.models.project import DbtReuseFromConfig


def build_dbt_reuse_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    current_manifest: DbtManifestIndex,
    adapter: BaseAdapter,
    adapter_name: str,
    dbt_model_plan: DbtModelPlanningResult | None,
    plan: DbtInteropPlan,
    dbt_options: DbtCliOptions,
    runner: DbtRunner,
    warnings: list[str] | None = None,
) -> DbtReusePlanningResult | None:
    """Build dbt reuse_from plan output when reuse_from is configured."""

    reuse_from: DbtReuseFromConfig = discovered_inputs.project_config.dbt.reuse_from
    if reuse_from.git_ref is None or reuse_from.generate_schema_name_override is None:
        return None
    if dbt_model_plan is None:
        return None

    try:
        compile_result: DbtReuseFromCompileResult = compile_reuse_from_manifest(
            sqlbuild_project_dir=project_dir,
            dbt_options=dbt_options,
            reuse_from=reuse_from,
            runner=runner,
        )
    except DbtReuseUnavailableError as error:
        if warnings is not None:
            warnings.append(f"dbt reuse_from skipped: {error.message}. Running standard build.")
        return None
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(compile_result.manifest_contents)
    )
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates_for_plan(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        plan=plan,
    )
    return build_dbt_reuse_planning_result(
        candidate_resolution=mark_missing_dbt_reuse_origin_relations(
            candidate_resolution=candidate_resolution,
            existing_origin_relation_keys=_existing_origin_relation_keys(
                project_dir=project_dir,
                discovered_inputs=discovered_inputs,
                adapter=adapter,
                adapter_name=adapter_name,
                candidate_resolution=candidate_resolution,
            ),
        ),
        dbt_model_plan=dbt_model_plan,
    )


def _existing_origin_relation_keys(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    candidate_resolution: DbtReuseCandidateResolution,
) -> frozenset[tuple[str | None, str | None, str]]:
    if not candidate_resolution.candidates:
        return frozenset()
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    connection: Any = adapter.connect(connection_config)
    try:
        existing: set[tuple[str | None, str | None, str]] = set()
        database: str | None
        for database in _origin_databases(candidate_resolution=candidate_resolution):
            relations: tuple[RelationInfo, ...] = adapter.list_relations(
                connection,
                database=database,
                schemas=_origin_schemas(
                    candidate_resolution=candidate_resolution, database=database
                ),
                names=_origin_names(candidate_resolution=candidate_resolution, database=database),
            )
            relation: RelationInfo
            for relation in relations:
                existing.add((relation.database, relation.schema, relation.name))
        return frozenset(existing)
    finally:
        adapter.close(connection)


def _origin_databases(
    *, candidate_resolution: DbtReuseCandidateResolution
) -> tuple[str | None, ...]:
    return tuple(
        dict.fromkeys(candidate.origin_database for candidate in candidate_resolution.candidates)
    )


def _origin_schemas(
    *, candidate_resolution: DbtReuseCandidateResolution, database: str | None
) -> tuple[str, ...] | None:
    schemas: tuple[str | None, ...] = tuple(
        dict.fromkeys(
            candidate.origin_schema
            for candidate in candidate_resolution.candidates
            if candidate.origin_database == database
        )
    )
    if any(schema is None for schema in schemas):
        return None
    return tuple(schema for schema in schemas if schema is not None)


def _origin_names(
    *, candidate_resolution: DbtReuseCandidateResolution, database: str | None
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            candidate.origin_name
            for candidate in candidate_resolution.candidates
            if candidate.origin_database == database
        )
    )


def build_dbt_dependency_baseline_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    current_manifest: DbtManifestIndex,
    adapter: BaseAdapter,
    adapter_name: str,
    dbt_model_plan: DbtModelPlanningResult | None,
    scoped_unique_ids: tuple[str, ...],
    dbt_options: DbtCliOptions,
    runner: DbtRunner,
    warnings: list[str] | None = None,
) -> DbtReusePlanningResult | None:
    """Build physical dependency baseline plan for unselected dbt refs."""

    if not scoped_unique_ids:
        return None
    reuse_from: DbtReuseFromConfig = discovered_inputs.project_config.dbt.reuse_from
    if reuse_from.git_ref is None or reuse_from.generate_schema_name_override is None:
        return None
    if dbt_model_plan is None:
        return None

    try:
        compile_result: DbtReuseFromCompileResult = compile_reuse_from_manifest(
            sqlbuild_project_dir=project_dir,
            dbt_options=dbt_options,
            reuse_from=reuse_from,
            runner=runner,
        )
    except DbtReuseUnavailableError:
        return None
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(compile_result.manifest_contents)
    )
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        scoped_unique_ids=scoped_unique_ids,
    )
    return build_dbt_reuse_planning_result(
        candidate_resolution=mark_missing_dbt_reuse_origin_relations(
            candidate_resolution=candidate_resolution,
            existing_origin_relation_keys=_existing_origin_relation_keys(
                project_dir=project_dir,
                discovered_inputs=discovered_inputs,
                adapter=adapter,
                adapter_name=adapter_name,
                candidate_resolution=candidate_resolution,
            ),
        ),
        dbt_model_plan=dbt_model_plan,
    )
