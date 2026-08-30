"""Tests for resolved verbose build-start context output."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.cli.commands._helpers.build_execution.run_context import write_build_run_context
from sqlbuild.cli.commands.models import SelectorFileSummary
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry
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
                "selected     1 of 2 managed resources",
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
            connection_config={"warehouse": {"secret": "nested"}},
            effective_vars={"start_date": {"secret": "nested"}},
            selector_files=(),
            full_refresh=False,
            expected_fragments=(
                "warehouse    not set",
                "full_refresh false",
                "date vars    not set",
            ),
            expected_absent_fragments=("nested", "Selection files"),
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
    )
    plan: PlanOutput = PlanOutput(
        model_entries=cast(tuple[ModelPlanEntry, ...], (object(),)),
        seed_entries=cast(tuple[SeedPlanEntry, ...], ()),
    )
    stream: StringIO = StringIO()

    write_build_run_context(
        stream=stream,
        command="sqb build",
        project=project,
        plan=plan,
        connection_config=test_case.connection_config,
        concurrency=5,
        full_refresh=test_case.full_refresh,
        selector_files=test_case.selector_files,
        use_color=False,
    )

    output: str = stream.getvalue()
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in output
