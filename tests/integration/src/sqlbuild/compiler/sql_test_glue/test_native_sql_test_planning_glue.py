"""SQL tests planned natively from compiled objects equal the JSON-request plans, test by test."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.sql_test_glue._test_types import (
    GeneratedSqlTestPlanningParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import (
    INVERTED_WINDOW,
    NO_WINDOW,
    VALID_WINDOW,
    PlanningCallOutcome,
    SqlTestCorpusShape,
    artifact_outcome,
    chain_outcome,
    compiled_project,
    generated_sql_test_files,
    native_raised_kinds,
    outcome_kind,
    planning_outcome,
    record_native_answers,
    use_sql_test_glue,
    with_unmocked_assertion,
)

_ADAPTERS: dict[str, BaseAdapter] = {
    "duckdb": DuckDbAdapter(),
    "postgres": PostgresAdapter(),
    "snowflake": SnowflakeAdapter(),
    "bigquery": BigQueryAdapter(),
    "sqlserver": SqlServerAdapter(),
}


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedSqlTestPlanningParityTestCase(
            description="mocks, expected outputs, assertions, helpers, windows and failing tests",
            seed=20261009,
            count=4,
            test_count=12,
            shape=SqlTestCorpusShape(
                windows=(NO_WINDOW, VALID_WINDOW, INVERTED_WINDOW),
                stray_window_share=0.1,
                helper_redefinition_share=0.15,
                assertion_share=0.2,
                unflattenable_assertion_share=0.1,
            ),
            adapter_names=("duckdb", "postgres", "snowflake", "bigquery", "sqlserver"),
            expected_minimum_native_planned=624,
            expected_minimum_native_with_errors=144,
            expected_minimum_native_chains=398,
            expected_minimum_native_raised=102,
            expected_native_raised_kinds=frozenset(
                {"compile_input", "planner_input", "sql_test_reference"}
            ),
            expected_minimum_answered_batches=0,
            expected_minimum_raised_outcomes=108,
        ),
        GeneratedSqlTestPlanningParityTestCase(
            description="multi-test batches that plan without window or helper errors",
            seed=20261010,
            count=3,
            test_count=12,
            shape=SqlTestCorpusShape(
                windows=(NO_WINDOW, VALID_WINDOW),
                stray_window_share=0.0,
                helper_redefinition_share=0.0,
                assertion_share=0.3,
                unflattenable_assertion_share=0.0,
            ),
            adapter_names=("duckdb", "postgres", "snowflake", "bigquery", "sqlserver"),
            expected_minimum_native_planned=1068,
            expected_minimum_native_with_errors=192,
            expected_minimum_native_chains=122,
            expected_minimum_native_raised=45,
            expected_native_raised_kinds=frozenset({"sql_test_reference"}),
            expected_minimum_answered_batches=30,
            expected_minimum_raised_outcomes=30,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_tests_when_planning_natively_then_plans_match_the_json_request(
    test_case: GeneratedSqlTestPlanningParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    native_answers: Counter[str] = record_native_answers(monkeypatch=monkeypatch)
    outcomes: Counter[str] = Counter()
    differences: list[tuple[object, object, object]] = []
    for index in range(test_case.count):
        project: CompiledProject = compiled_project(
            project_dir=tmp_path / f"project_{index}",
            files=generated_sql_test_files(
                rng=rng, test_count=test_case.test_count, shape=test_case.shape
            ),
        )
        batches: tuple[tuple[CompiledSqlTest, ...], ...] = (
            project.sql_tests,
            *((test,) for test in project.sql_tests),
            (with_unmocked_assertion(project=project),),
        )
        for adapter_name in test_case.adapter_names:
            adapter: BaseAdapter = _ADAPTERS[adapter_name]
            for render_sql in (False, True):
                inputs: list[object] = []
                expected: list[object] = []
                actual: list[object] = []
                for tests in batches:
                    use_sql_test_glue(monkeypatch=monkeypatch, enabled=False)
                    expected.append(
                        planning_outcome(
                            project=project, tests=tests, adapter=adapter, render_sql=render_sql
                        )
                    )
                    use_sql_test_glue(monkeypatch=monkeypatch, enabled=True)
                    actual.append(
                        planning_outcome(
                            project=project, tests=tests, adapter=adapter, render_sql=render_sql
                        )
                    )
                    inputs.append((adapter_name, render_sql, tuple(test.name for test in tests)))
                differences.extend(mismatches(inputs=inputs, expected=expected, actual=actual))
                outcomes.update(map(outcome_kind, actual[1:]))
                outcomes[f"batch_{outcome_kind(actual[0])}"] += 1
            differences.extend(
                mismatches(
                    inputs=[(adapter_name, "artifacts", tests) for tests in batches],
                    expected=[
                        artifact_outcome(project=project, tests=tests, adapter=adapter, glue=False)
                        for tests in batches
                    ],
                    actual=[
                        artifact_outcome(project=project, tests=tests, adapter=adapter, glue=True)
                        for tests in batches
                    ],
                )
            )
        use_sql_test_glue(monkeypatch=monkeypatch, enabled=False)
        python_chains: PlanningCallOutcome = chain_outcome(project=project, tests=project.sql_tests)
        use_sql_test_glue(monkeypatch=monkeypatch, enabled=True)
        native_chains: PlanningCallOutcome = chain_outcome(project=project, tests=project.sql_tests)
        differences.extend(
            mismatches(inputs=["chains"], expected=[python_chains], actual=[native_chains])
        )

    assert (
        differences,
        native_answers["native_planned"] >= test_case.expected_minimum_native_planned,
        native_answers["native_with_errors"] >= test_case.expected_minimum_native_with_errors,
        native_answers["native_chains"] >= test_case.expected_minimum_native_chains,
        native_answers["native_raised"] >= test_case.expected_minimum_native_raised,
        native_raised_kinds(answers=native_answers) >= test_case.expected_native_raised_kinds,
        outcomes["batch_answered"] >= test_case.expected_minimum_answered_batches,
        outcomes["raised"] >= test_case.expected_minimum_raised_outcomes,
    ) == ([], True, True, True, True, True, True, True), (native_answers, outcomes)
