"""Build an adapted SQLBuild project for `sqb dbt scenario test`, warehouse-direct."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.main.cli.enforce_standard_mode import (
    enforce_dbt_interop_standard_mode,
)
from sqlbuild.integrations.dbt.main.cli.resolve_executable import resolve_dbt_executable
from sqlbuild.integrations.dbt.main.config.resolve_plan_options import resolve_dbt_plan_options
from sqlbuild.integrations.dbt.main.profile.resolve_connection_config import (
    resolve_connection_config,
)
from sqlbuild.integrations.dbt.main.runtime.report_progress import report_progress
from sqlbuild.integrations.dbt.main.runtime.resolve_interop_adapter import (
    resolve_dbt_interop_adapter,
)
from sqlbuild.integrations.dbt.main.selection.adapt_project_for_scenarios import (
    adapt_project_for_dbt_scenarios,
)
from sqlbuild.integrations.dbt.main.selection.resolve_scenario_target_names import (
    resolve_dbt_scenario_target_names,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtScenarioBuild
from sqlbuild.integrations.dbt.pipeline.helpers.interop_prologue import (
    load_compiled_dbt_manifest,
)
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.resolution.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)


def build_dbt_scenario_project(
    *,
    project_dir: Path,
    expected_model_names: tuple[str, ...],
    select: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str | None = None,
    no_sql_validation: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> DbtScenarioBuild:
    """Compile dbt, adapt dbt models, and return the adapted SQLBuild project."""

    dbt_executable = dbt_executable or resolve_dbt_executable()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=(),
    )
    runner: DbtRunner = dbt_runner or DbtRunner(dbt_executable=dbt_executable)
    manifest: DbtManifestIndex = load_compiled_dbt_manifest(
        runner=runner,
        dbt_options=dbt_options,
        full_refresh=True,
        on_progress=on_progress,
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(
        adapter_name=adapter_name, project_dir=project_dir
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    report_progress(on_progress=on_progress, message="Compiled SQLBuild project.")
    target_names: tuple[str, ...] = resolve_dbt_scenario_target_names(
        project=project,
        manifest=manifest,
        selected_dbt_unique_ids=tuple(manifest.models_by_unique_id),
        select=expected_model_names or select,
    )
    adapted_project: CompiledProject = adapt_project_for_dbt_scenarios(
        project=project,
        manifest=manifest,
        target_names=target_names,
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    return DbtScenarioBuild(
        project=adapted_project,
        adapter_name=adapter_name,
        connection_config=connection_config,
        project_name=discovered_inputs.project_config.name,
        scenario_config=resolve_effective_scenario_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
    )
