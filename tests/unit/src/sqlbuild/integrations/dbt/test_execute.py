from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.planning.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandExecutionResult,
    DbtExecutionOutcome,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers import execute as execute_helpers
from sqlbuild.integrations.dbt.pipeline.main import execute as execute_module
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
)
from sqlbuild.spec.models.project import (
    DbtConfig,
    DbtReuseFromConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtCompileFullRefreshPipelineTestCase,
    DbtExecutionSelectionStatusTestCase,
    DbtExecutionSpacingTestCase,
    DbtExecutionSummaryFooterTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    CompileOnlyDbtRunner,
    emit_connection_progress,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionSelectionStatusTestCase(
            description="prints dbt execution selection status for non tty streams",
            expected_total=2,
            expected_output_fragment="Resolving dbt execution selection...",
            expected_completion_fragment="Resolved dbt execution selection.",
        )
    ],
    ids=["prints dbt execution selection status for non tty streams"],
)
def test_given_non_tty_stream_when_resolving_dbt_execution_total_then_prints_status(
    test_case: DbtExecutionSelectionStatusTestCase,
) -> None:
    class StubRunner:
        def invoke(self, **kwargs: object) -> object:
            del kwargs
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"unique_id":"model.analytics.orders","resource_type":"model"}\n'
                    '{"unique_id":"model.analytics.customers","resource_type":"model"}\n'
                ),
            )

    stream: StringIO = StringIO()

    total: int | None = execute_helpers._dbt_execution_expected_total(
        runner=cast(DbtRunner, StubRunner()),
        options=DbtCliOptions(project_dir=Path("/dbt_project")),
        argv=("dbt", "build", "--select", "orders"),
        stream=stream,
        use_color=False,
    )

    assert total == test_case.expected_total
    output: str = stream.getvalue()
    assert test_case.expected_output_fragment in output
    assert test_case.expected_completion_fragment in output


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
            dbt=DbtConfig(
                project_dir="../dbt_project",
                reuse_from=DbtReuseFromConfig(
                    git_ref="main",
                    generate_schema_name_override="dbt/macros/prod_generate_schema_name.sql",
                ),
            ),
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
        lambda *, manifest_path: SimpleNamespace(
            models_by_unique_id={},
            seeds_by_unique_id={},
            seed_identity_warnings=(),
        ),
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
            models=(),
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCompileFullRefreshPipelineTestCase(
            description="dbt test compiles with full refresh",
            command="test",
            expected_full_refresh_values=(True,),
        )
    ],
    ids=["dbt test compiles with full refresh"],
)
def test_given_dbt_test_command_when_executing_then_compiles_with_full_refresh(
    test_case: DbtCompileFullRefreshPipelineTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(query_change_tracking=False),
            dbt=DbtConfig(
                project_dir="../dbt_project",
                reuse_from=DbtReuseFromConfig(
                    git_ref="main",
                    generate_schema_name_override="dbt/macros/prod_generate_schema_name.sql",
                ),
            ),
        ),
        local_config=LocalConfig(),
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand(test_case.command),
        dbt_command_argv=("dbt", "test", "--select", "missing"),
        dbt_ls_nodes=(
            DbtLsNode(
                unique_id="model.analytics.orders",
                resource_type="model",
                package_name="analytics",
                name="orders",
                fqn=("analytics", "orders"),
            ),
        ),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
    runner: CompileOnlyDbtRunner = CompileOnlyDbtRunner()

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
        lambda *, manifest_path: SimpleNamespace(
            models_by_unique_id={},
            seeds_by_unique_id={},
            seed_identity_warnings=(),
        ),
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
            models=(),
        ),
    )
    monkeypatch.setattr(execute_module, "build_dbt_combined_graph", lambda **kwargs: object())
    monkeypatch.setattr(execute_module, "plan_dbt_interop_command", lambda **kwargs: plan)
    monkeypatch.setattr(execute_module, "build_dbt_model_plan_output", lambda **kwargs: None)
    monkeypatch.setattr(execute_module, "build_dbt_non_model_run_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_seed_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_test_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_merged_dbt_execution_argv", lambda **kwargs: None)
    monkeypatch.setattr(execute_module, "build_effective_connection_config", lambda **kwargs: {})
    monkeypatch.setattr(execute_module, "resolve_connection_config", lambda **kwargs: {})
    monkeypatch.setattr(
        execute_module,
        "execute_dbt_commands",
        lambda **kwargs: DbtCommandExecutionResult(returncode=0),
    )
    monkeypatch.setattr(
        execute_module,
        "build_dbt_execution_outcome",
        lambda **kwargs: DbtExecutionOutcome(),
    )

    output_stream: StringIO = StringIO()

    exit_code: int = execute_module.execute_dbt_interop_from_project(
        command=DbtInteropCommand(test_case.command),
        project_dir=Path("/sqlbuild_project"),
        args=("--select", "missing"),
        dbt_runner=runner,
        progress_stream=output_stream,
        dbt_stdout_stream=StringIO(),
        use_color=False,
    )

    assert exit_code == 0
    assert tuple(runner.compile_full_refresh_values) == test_case.expected_full_refresh_values
    assert "dbt reuse" not in output_stream.getvalue()


SUMMARY_FOOTER_TEST_CASES: list[DbtExecutionSummaryFooterTestCase] = [
    DbtExecutionSummaryFooterTestCase(
        description="counts mixed dbt node statuses with errors into footer",
        node_statuses=("ok", "success", "warn", "error", "skipped"),
        expected_footer=(
            "Completed with errors.\nPASS=2  WARN=1  FAIL=1  SKIP=1  TOTAL=5  (0.00s)"
        ),
    ),
    DbtExecutionSummaryFooterTestCase(
        description="reports warnings status when a node warns without failing",
        node_statuses=("ok", "warn"),
        expected_footer=(
            "Completed with warnings.\nPASS=1  WARN=1  FAIL=0  SKIP=0  TOTAL=2  (0.00s)"
        ),
    ),
    DbtExecutionSummaryFooterTestCase(
        description="reports success status when all nodes pass",
        node_statuses=("ok", "success"),
        expected_footer="Completed successfully.\nPASS=2  WARN=0  FAIL=0  SKIP=0  TOTAL=2  (0.00s)",
    ),
    DbtExecutionSummaryFooterTestCase(
        description="returns no footer when there are no dbt node results",
        node_statuses=(),
        expected_footer=None,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUMMARY_FOOTER_TEST_CASES,
    ids=[case.description for case in SUMMARY_FOOTER_TEST_CASES],
)
def test_given_dbt_node_results_when_rendering_summary_footer_then_counts_statuses(
    test_case: DbtExecutionSummaryFooterTestCase,
) -> None:
    node_results: tuple[DbtNodeExecutionResult, ...] = tuple(
        DbtNodeExecutionResult(
            unique_id=f"model.analytics.node_{index}",
            resource_type="model",
            node_name=f"node_{index}",
            status=status,
            index=index + 1,
            total=len(test_case.node_statuses),
            execution_time=0.0,
        )
        for index, status in enumerate(test_case.node_statuses)
    )

    footer: str | None = execute_helpers.render_dbt_execution_summary_footer(
        node_results=node_results,
        use_color=False,
    )

    assert footer == test_case.expected_footer
