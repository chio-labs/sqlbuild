"""Build an adapted SQLBuild project for `sqb dbt scenario test`, warehouse-direct."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.operations.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.manifest.core import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.selection.sql_test_targets import (
    adapt_project_for_dbt_scenarios,
    resolve_dbt_scenario_target_names,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtScenarioBuild,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import dbt_failure_detail
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.integrations.dbt.shared.helpers.executable import resolve_dbt_executable
from sqlbuild.spec.models.project import (
    resolve_effective_adapter_name,
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
    _report(on_progress, "Compiling dbt project...")
    compile_result: DbtCommandResult = runner.compile(options=dbt_options, full_refresh=True)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError("dbt compile failed", help=dbt_failure_detail(compile_result))
    manifest_path: Path = resolve_dbt_manifest_path(options=dbt_options)
    manifest: DbtManifestIndex = load_dbt_manifest_index(manifest_path=manifest_path)
    _report(on_progress, "Loaded dbt manifest.")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    _report(on_progress, "Compiled SQLBuild project.")
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


def _report(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
