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
    DbtLsNode,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_output import (
    format_dbt_reuse_execution_output,
)
from sqlbuild.integrations.dbt.pipeline.main import execute as execute_module
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtReusePlanAction,
    DbtReusePlanReason,
)
from sqlbuild.shared.helpers.display import DisplayOptions
from sqlbuild.spec.models.project import (
    DbtConfig,
    DbtReuseFromConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtCompileFullRefreshPipelineTestCase,
    DbtExecutionSpacingTestCase,
    DbtReuseExecutionOrderingTestCase,
    DbtReuseExecutionOutputTestCase,
)
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
            models=(),
        ),
    )
    monkeypatch.setattr(execute_module, "build_dbt_combined_graph", lambda **kwargs: object())
    monkeypatch.setattr(execute_module, "plan_dbt_interop_command", lambda **kwargs: plan)
    monkeypatch.setattr(execute_module, "build_dbt_model_plan_output", lambda **kwargs: None)
    monkeypatch.setattr(
        execute_module,
        "build_dbt_reuse_plan_output",
        lambda **kwargs: pytest.fail("dbt test should not plan dbt reuse"),
    )
    monkeypatch.setattr(
        execute_module,
        "build_dbt_dependency_baseline_plan_output",
        lambda **kwargs: pytest.fail("dbt test should not plan dependency baseline reuse"),
    )
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecutionOutputTestCase(
            description="formats styled reuse and baseline reuse rows with overflow",
            reused_unique_ids=("model.analytics.fact_orders",),
            baseline_reused_unique_ids=(
                "model.analytics.events",
                "snapshot.analytics.orders_snapshot",
            ),
            max_entries_per_section=2,
            dbt_execution_will_run=True,
            expected_fragments=(
                "dbt reuse  pre-phase before dbt execution",
                "model.analytics.fact_orders",
                "OK     reuse",
                "model.analytics.events",
                "OK     baseline reuse before dbt catch-up",
                "... and 1 more (use --verbose to show all)",
                "REUSED=1  BASELINE_REUSED=2  TOTAL=3",
            ),
            expected_absent_fragments=("snapshot.analytics.orders_snapshot",),
            expected_color_fragments=(
                "\033[38;5;208m\033[1mdbt reuse\033[0m",
                "\033[32mOK\033[0m",
            ),
        )
    ],
    ids=["formats styled reuse and baseline reuse rows with overflow"],
)
def test_given_dbt_reuse_execution_when_formatting_then_outputs_clear_pre_phase_rows(
    test_case: DbtReuseExecutionOutputTestCase,
) -> None:
    plan: DbtReusePlanningResult = DbtReusePlanningResult(
        entries=(
            DbtReusePlanEntry(
                unique_id="model.analytics.fact_orders",
                action=DbtReusePlanAction.COMPLETE_REUSE,
                reason=DbtReusePlanReason.DESTINATION_MISSING,
            ),
            DbtReusePlanEntry(
                unique_id="model.analytics.events",
                action=DbtReusePlanAction.SEEDED_REUSE,
                reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
            ),
            DbtReusePlanEntry(
                unique_id="snapshot.analytics.orders_snapshot",
                action=DbtReusePlanAction.SEEDED_REUSE,
                reason=DbtReusePlanReason.DESTINATION_MISSING,
            ),
        )
    )

    no_color_output: str = format_dbt_reuse_execution_output(
        plan=plan,
        reused_unique_ids=test_case.reused_unique_ids,
        baseline_reused_unique_ids=test_case.baseline_reused_unique_ids,
        use_color=False,
        dbt_execution_will_run=test_case.dbt_execution_will_run,
        display_options=DisplayOptions(max_entries_per_section=test_case.max_entries_per_section),
    )
    color_output: str = format_dbt_reuse_execution_output(
        plan=plan,
        reused_unique_ids=test_case.reused_unique_ids,
        baseline_reused_unique_ids=test_case.baseline_reused_unique_ids,
        use_color=True,
        dbt_execution_will_run=test_case.dbt_execution_will_run,
        display_options=DisplayOptions(max_entries_per_section=test_case.max_entries_per_section),
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in no_color_output
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in no_color_output
    assert "\033[" not in no_color_output
    for expected_color_fragment in test_case.expected_color_fragments:
        assert expected_color_fragment in color_output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecutionOrderingTestCase(
            description="prints plan before dbt reuse pre-phase and dbt execution",
            expected_ordered_fragments=(
                "Plan ready",
                "dbt reuse  pre-phase before dbt execution",
                "dbt execution  dbt build",
            ),
            expected_fragments=(
                "model.analytics.fact_orders",
                "OK     reuse",
                "model.analytics.events",
                "OK     baseline reuse before dbt catch-up",
            ),
            expected_absent_fragments=("Preparing dbt reuse relations",),
        )
    ],
    ids=["prints plan before dbt reuse pre-phase and dbt execution"],
)
def test_given_dbt_reuse_execution_when_running_then_prints_plan_before_reuse_pre_phase(
    test_case: DbtReuseExecutionOrderingTestCase,
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
    reuse_plan: DbtReusePlanningResult = DbtReusePlanningResult(
        entries=(
            DbtReusePlanEntry(
                unique_id="model.analytics.fact_orders",
                action=DbtReusePlanAction.COMPLETE_REUSE,
                reason=DbtReusePlanReason.DESTINATION_MISSING,
            ),
            DbtReusePlanEntry(
                unique_id="model.analytics.events",
                action=DbtReusePlanAction.SEEDED_REUSE,
                reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
            ),
        )
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build", "--select", "model.analytics.events"),
        dbt_ls_nodes=(DbtLsNode(unique_id="model.analytics.events", resource_type="model"),),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
    output_stream: StringIO = StringIO()

    class Adapter:
        adapter_name: str = "duckdb"

        def connect(self, config: dict[str, object]) -> object:
            del config
            return object()

        def close(self, connection: object) -> None:
            del connection

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
        execute_module, "resolve_dbt_interop_adapter", lambda *args, **kwargs: Adapter()
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
    monkeypatch.setattr(execute_module, "build_dbt_reuse_plan_output", lambda **kwargs: reuse_plan)
    monkeypatch.setattr(
        execute_module,
        "execute_dbt_complete_reuse_plan",
        lambda **kwargs: ("model.analytics.fact_orders",),
    )
    monkeypatch.setattr(
        execute_module,
        "execute_dbt_seeded_reuse_plan",
        lambda **kwargs: ("model.analytics.events",),
    )
    monkeypatch.setattr(execute_module, "build_dbt_non_model_run_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_seed_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(execute_module, "build_dbt_pruned_test_unique_ids", lambda **kwargs: ())
    monkeypatch.setattr(
        execute_module,
        "build_merged_dbt_execution_argv",
        lambda **kwargs: ("dbt", "build", "--select", "model.analytics.events"),
    )
    monkeypatch.setattr(execute_module, "build_effective_connection_config", lambda **kwargs: {})
    monkeypatch.setattr(execute_module, "resolve_connection_config", lambda **kwargs: {})

    def execute_dbt_work(**kwargs: object) -> DbtCommandExecutionResult:
        output: StringIO = cast(StringIO, kwargs["progress_stream"])
        output.write("dbt execution  dbt build\n")
        return DbtCommandExecutionResult(returncode=0)

    monkeypatch.setattr(execute_module, "execute_dbt_commands", execute_dbt_work)
    monkeypatch.setattr(
        execute_module,
        "build_dbt_execution_outcome",
        lambda **kwargs: DbtExecutionOutcome(),
    )

    exit_code: int = execute_module.execute_dbt_interop_from_project(
        command=DbtInteropCommand.BUILD,
        project_dir=Path("/sqlbuild_project"),
        args=("--select", "model.analytics.events"),
        dbt_runner=CompileOnlyDbtRunner(),
        progress_stream=output_stream,
        dbt_stdout_stream=output_stream,
        use_color=False,
    )

    rendered: str = output_stream.getvalue()
    assert exit_code == 0
    previous_index: int = -1
    for expected_fragment in test_case.expected_ordered_fragments:
        current_index: int = rendered.index(expected_fragment)
        assert current_index > previous_index
        previous_index = current_index
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in rendered
