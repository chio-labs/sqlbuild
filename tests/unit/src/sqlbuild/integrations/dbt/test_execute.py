from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandExecutionResult,
    DbtExecutionOutcome,
    DbtInteropPlan,
    DbtInteropSelectionResult,
)
from sqlbuild.integrations.dbt.pipeline.main import execute as execute_module
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.spec.models.project import DbtConfig, LocalConfig, ProjectConfig, SettingsConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtExecutionSpacingTestCase
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    CompileOnlyDbtRunner,
    emit_connection_progress,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSpacingTestCase(
            description="keeps one blank line between connection and plan output",
            expected_spacing_fragment="Connected to duckdb. (0.00s)\n\nPlan ready",
            expected_no_work_spacing_fragment="Skipping dbt: no dbt work selected.\n\n"
            "No SQLBuild work selected.",
            unexpected_no_blank_fragment="Connected to duckdb. (0.00s)\nPlan ready",
            unexpected_no_work_no_blank_fragment="Skipping dbt: no dbt work selected.\n"
            "No SQLBuild work selected.",
            unexpected_extra_blank_fragment="Connected to duckdb. (0.00s)\n\n\nPlan ready",
            unexpected_no_work_extra_blank_fragment="Skipping dbt: no dbt work selected.\n\n\n"
            "No SQLBuild work selected.",
        )
    ],
    ids=["keeps one blank line between connection and plan output"],
)
def test_given_execution_plan_output_when_rendering_after_connection_then_keeps_one_blank_line(
    test_case: DbtExecutionSpacingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(query_change_tracking=False),
            dbt=DbtConfig(project_dir="../dbt_project"),
        ),
        local_config=LocalConfig(),
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build", "--select", "missing"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
    output_stream: StringIO = StringIO()

    monkeypatch.setattr(
        execute_module, "discover_project_inputs", lambda *, project_dir: discovered_inputs
    )
    monkeypatch.setattr(
        execute_module,
        "resolve_dbt_plan_options",
        lambda **kwargs: DbtCliOptions(project_dir=Path("/dbt_project")),
    )
    monkeypatch.setattr(
        execute_module, "resolve_dbt_manifest_path", lambda *, options: Path("/manifest.json")
    )
    monkeypatch.setattr(
        execute_module,
        "load_dbt_manifest_index",
        lambda *, manifest_path: SimpleNamespace(models_by_unique_id={}),
    )
    monkeypatch.setattr(execute_module, "resolve_effective_adapter_name", lambda **kwargs: "duckdb")
    monkeypatch.setattr(
        execute_module, "resolve_dbt_interop_adapter", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(
        execute_module,
        "build_compiled_project",
        lambda **kwargs: SimpleNamespace(
            settings=SimpleNamespace(query_change_tracking=False),
            run_id="run",
            effective_target_database=None,
            effective_target_schema="main",
            effective_target_name="dev",
        ),
    )
    monkeypatch.setattr(execute_module, "build_dbt_combined_graph", lambda **kwargs: object())
    monkeypatch.setattr(execute_module, "plan_dbt_interop_command", lambda **kwargs: plan)
    monkeypatch.setattr(execute_module, "build_dbt_model_plan_output", emit_connection_progress)
    monkeypatch.setattr(execute_module, "build_dbt_non_model_run_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_seed_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_test_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_merged_dbt_execution_argv", lambda **kwargs: None)
    monkeypatch.setattr(execute_module, "build_effective_connection_config", lambda **kwargs: {})
    monkeypatch.setattr(execute_module, "resolve_connection_config", lambda **kwargs: {})

    def execute_no_dbt_work(**kwargs: object) -> DbtCommandExecutionResult:
        output: StringIO = cast(StringIO, kwargs["progress_stream"])
        output.write("Skipping dbt: no dbt work selected.\n")
        return DbtCommandExecutionResult(returncode=0)

    monkeypatch.setattr(execute_module, "execute_dbt_commands", execute_no_dbt_work)
    monkeypatch.setattr(
        execute_module,
        "build_dbt_execution_outcome",
        lambda **kwargs: DbtExecutionOutcome(),
    )

    def write_progress(message: str) -> None:
        output_stream.write(f"{message}\n")

    exit_code: int = execute_module.execute_dbt_interop_from_project(
        command=DbtInteropCommand.BUILD,
        project_dir=Path("/sqlbuild_project"),
        args=("--select", "missing"),
        dbt_runner=CompileOnlyDbtRunner(),
        on_progress=write_progress,
        progress_stream=output_stream,
        dbt_stdout_stream=output_stream,
        use_color=False,
    )

    rendered: str = output_stream.getvalue()
    assert exit_code == 0
    assert test_case.expected_spacing_fragment in rendered
    assert test_case.expected_no_work_spacing_fragment in rendered
    assert test_case.unexpected_no_blank_fragment not in rendered
    assert test_case.unexpected_no_work_no_blank_fragment not in rendered
    assert test_case.unexpected_extra_blank_fragment not in rendered
    assert test_case.unexpected_no_work_extra_blank_fragment not in rendered
