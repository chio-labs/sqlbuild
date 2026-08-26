from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.build.classes.build_scheduler import _test_result_authored_order
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from tests.unit.src.sqlbuild.executor.build.classes._test_types import (
    SqlTestAuthoredOrderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestAuthoredOrderTestCase(
            description="case index preserves authored order instead of alphabetical names",
            case_names=("zebra", "alpha"),
            expected_order=("zebra", "alpha"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_out_of_order_case_names_when_sorting_build_results_then_authored_order_is_preserved(
    test_case: SqlTestAuthoredOrderTestCase,
) -> None:
    source_path: Path = Path("tests/unit/status.sql")
    entries: tuple[SqlTestPlanEntry, ...] = tuple(
        SqlTestPlanEntry(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_TEST,
                name=f"status [{case_name}]",
            ),
            name=f"status [{case_name}]",
            source_path=source_path,
            block_index=1,
            case_name=case_name,
            case_index=case_index,
        )
        for case_index, case_name in enumerate(test_case.case_names)
    )
    plan: PlanOutput = PlanOutput(test_entries=entries)
    results: list[SqlTestExecutionResult] = [
        SqlTestExecutionResult(
            test_name=entry.name,
            outcome=SqlTestOutcome.PASS,
            source_path=entry.source_path,
            block_index=entry.block_index,
            case_name=entry.case_name,
            case_index=entry.case_index,
        )
        for entry in reversed(entries)
    ]

    ordered: list[SqlTestExecutionResult] = sorted(
        results,
        key=lambda result: _test_result_authored_order(plan=plan, result=result),
    )

    assert tuple(result.case_name for result in ordered) == test_case.expected_order
