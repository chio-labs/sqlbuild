"""Tests for resolved verbose build-start context output."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.cli.commands._helpers.build_execution.run_context import (
    write_build_run_context,
)
from sqlbuild.cli.commands.models import BuildRunContext, SelectorFileSummary
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompiledSource
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredTaskFunction
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SourceLoadPlanEntry,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.build_execution._test_types import (
    BuildRunContextTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildRunContextTestCase(
            description="resolved placement dates and selector summary",
            connection_config={
                "warehouse": "PROD_WH__LARGE",
                "password": "never-print-password",
                "token": "never-print-token",
                "authenticator": "never-print-authenticator",
            },
            effective_vars={
                "start_date": "1970-01-01",
                "end_date": "2030-12-31",
                "api_secret": "never-print-var",
            },
            selector_files=(
                SelectorFileSummary(
                    path=Path("/tmp/sqlbuild-dagster-select.txt"), selector_count=386
                ),
            ),
            full_refresh=True,
            expected_fragments=(
                "Execution",
                "command      sqb build",
                "run_id       20260830T175430Z_fb5fb40a8b81",
                "target       test",
                "database     RACING",
                "schema       DEV_DAGSTER_DEV",
                "warehouse    PROD_WH__LARGE",
                "concurrency  5 configured limit",
                "full_refresh true",
                "selected     1 of 2 build resources",
                "date vars    1970-01-01 to 2030-12-31",
                "Selection files",
                "selector_file /tmp/sqlbuild-dagster-select.txt (386 selectors)",
            ),
            expected_absent_fragments=(
                "never-print-password",
                "never-print-token",
                "never-print-authenticator",
                "never-print-var",
            ),
        ),
        BuildRunContextTestCase(
            description="missing optional placement and unsafe date values",
            connection_config={"warehouse": "safe\nforged"},
            effective_vars={"start_date": "never-print-date-secret", "end_date": "2030-12-31"},
            selector_files=(SelectorFileSummary(path=Path("unsafe\npath"), selector_count=1),),
            full_refresh=False,
            expected_fragments=(
                "warehouse    safe\\x0aforged",
                "full_refresh false",
                "date vars    end_date=2030-12-31",
                "unsafe\\x0apath",
            ),
            expected_absent_fragments=("never-print-date-secret", "safe\nforged", "unsafe\npath"),
        ),
        BuildRunContextTestCase(
            description="python and source resources use the full build graph count",
            connection_config={},
            effective_vars={},
            selector_files=(),
            full_refresh=False,
            expected_fragments=("selected     3 of 4 build resources",),
            expected_absent_fragments=(),
            selected_source_count=1,
            selected_python_count=1,
            total_source_count=1,
            total_task_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_resolved_build_context_when_writing_then_renders_safe_verbose_summary(
    test_case: BuildRunContextTestCase,
) -> None:
    project: CompiledProject = CompiledProject(
        run_id="20260830T175430Z_fb5fb40a8b81",
        effective_target_name="test",
        effective_connection={},
        effective_vars=test_case.effective_vars,
        effective_target_database="RACING",
        effective_target_schema="DEV_DAGSTER_DEV",
        models=cast(tuple[CompiledModel, ...], (object(), object())),
        sources=cast(
            tuple[CompiledSource, ...],
            tuple(
                SimpleNamespace(source_entry=SimpleNamespace(loader="load_orders"))
                for _ in range(test_case.total_source_count)
            ),
        ),
    )
    plan: PlanOutput = PlanOutput(
        model_entries=cast(tuple[ModelPlanEntry, ...], (object(),)),
        seed_entries=cast(tuple[SeedPlanEntry, ...], ()),
        source_load_entries=cast(
            tuple[SourceLoadPlanEntry, ...],
            tuple(object() for _ in range(test_case.selected_source_count)),
        ),
    )
    stream: StringIO = StringIO()

    write_build_run_context(
        stream=stream,
        context=BuildRunContext(
            command="sqb build",
            project=project,
            plan=plan,
            discovered_inputs=DiscoveredProjectInputs(
                project_config=ProjectConfig(name="test", adapter="duckdb"),
                local_config=LocalConfig(),
                task_functions=cast(
                    tuple[DiscoveredTaskFunction, ...],
                    tuple(object() for _ in range(test_case.total_task_count)),
                ),
            ),
            python_plan_entries=cast(
                tuple[PythonPlanEntry, ...],
                tuple(object() for _ in range(test_case.selected_python_count)),
            ),
            connection_config=test_case.connection_config,
            concurrency=5,
            full_refresh=test_case.full_refresh,
            selector_files=test_case.selector_files,
        ),
        use_color=False,
    )

    output: str = stream.getvalue()
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in output
