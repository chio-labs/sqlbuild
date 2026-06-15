"""dbt reuse_from planning pipeline helpers."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.reuse_candidates import (
    build_dbt_reuse_planning_result,
    resolve_dbt_reuse_candidates_for_plan,
)
from sqlbuild.integrations.dbt.helpers.reuse_from import compile_reuse_from_manifest
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtInteropPlan,
    DbtModelPlanningResult,
    DbtReuseFromCompileResult,
    DbtReusePlanningResult,
)
from sqlbuild.spec.models.project import DbtReuseFromConfig


def build_dbt_reuse_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    current_manifest: DbtManifestIndex,
    dbt_model_plan: DbtModelPlanningResult | None,
    plan: DbtInteropPlan,
    dbt_options: DbtCliOptions,
    runner: DbtRunner,
) -> DbtReusePlanningResult | None:
    """Build dbt reuse_from plan output when reuse_from is configured."""

    reuse_from: DbtReuseFromConfig = discovered_inputs.project_config.dbt.reuse_from
    if reuse_from.git_ref is None or reuse_from.generate_schema_name_override is None:
        return None
    if dbt_model_plan is None:
        return None

    compile_result: DbtReuseFromCompileResult = compile_reuse_from_manifest(
        sqlbuild_project_dir=project_dir,
        dbt_options=dbt_options,
        reuse_from=reuse_from,
        runner=runner,
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(compile_result.manifest_contents)
    )
    return build_dbt_reuse_planning_result(
        candidate_resolution=resolve_dbt_reuse_candidates_for_plan(
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            plan=plan,
        ),
        dbt_model_plan=dbt_model_plan,
    )
