from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledDirectLogicSqlTestPayload,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.main.execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.planner.helpers.sql_test_assembly._test_types import (
    ExecuteChainTestCase,
    ExecuteMacroTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.helpers.sql_test_assembly.helpers import (
    build_test_and_project,
)

EXECUTE_CHAIN_TEST_CASES: list[ExecuteChainTestCase] = [
    ExecuteChainTestCase(
        description=("single model with source mock executes and produces expected rows"),
        model_queries={
            "stg_orders": ('SELECT id, amount * 2 AS doubled FROM __source("raw_orders")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw_orders": ("SELECT 1 AS id, 100 AS amount UNION ALL SELECT 2 AS id, 200 AS amount"),
        },
        helper_ctes={},
        expected_model_names=("stg_orders",),
        expected_cte_bodies={
            "stg_orders": (
                "SELECT 1 AS id, 200 AS doubled UNION ALL SELECT 2 AS id, 400 AS doubled"
            ),
        },
        expected_chain_length=1,
        expected_results={
            "stg_orders": ((1, 200), (2, 400)),
        },
    ),
    ExecuteChainTestCase(
        description=("two model chain produces correct intermediate and final results"),
        model_queries={
            "stg_orders": ('SELECT id, amount FROM __source("raw")'),
            "fact_orders": ('SELECT id, amount + 10 AS adjusted FROM __ref("stg_orders")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id, 100 AS amount",
        },
        helper_ctes={},
        expected_model_names=("stg_orders", "fact_orders"),
        expected_cte_bodies={
            "stg_orders": "SELECT 1 AS id, 100 AS amount",
            "fact_orders": "SELECT 1 AS id, 110 AS adjusted",
        },
        expected_chain_length=2,
        expected_results={
            "stg_orders": ((1, 100),),
            "fact_orders": ((1, 110),),
        },
    ),
    ExecuteChainTestCase(
        description=("three model chain A to B to C with arithmetic at each stage"),
        model_queries={
            "A": 'SELECT id, amount FROM __source("raw")',
            "B": ('SELECT id, amount * 2 AS doubled FROM __ref("A")'),
            "C": ('SELECT id, doubled + 1 AS final FROM __ref("B")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id, 50 AS amount",
        },
        helper_ctes={},
        expected_model_names=("A", "B", "C"),
        expected_cte_bodies={
            "A": "SELECT 1 AS id, 50 AS amount",
            "B": "SELECT 1 AS id, 100 AS doubled",
            "C": "SELECT 1 AS id, 101 AS final",
        },
        expected_chain_length=3,
        expected_results={
            "A": ((1, 50),),
            "B": ((1, 100),),
            "C": ((1, 101),),
        },
    ),
    ExecuteChainTestCase(
        description=("helper cte feeds into mock and result is executable"),
        model_queries={
            "orders": ('SELECT id, amount FROM __ref("raw_orders")'),
        },
        mock_ref_ctes={
            "raw_orders": ("SELECT id, base_amount * 3 AS amount FROM gen_amounts"),
        },
        mock_source_ctes={},
        helper_ctes={
            "gen_amounts": ("SELECT 1 AS id, 10 AS base_amount"),
        },
        expected_model_names=("orders",),
        expected_cte_bodies={
            "orders": "SELECT 1 AS id, 30 AS amount",
        },
        expected_chain_length=1,
        expected_results={
            "orders": ((1, 30),),
        },
    ),
    ExecuteChainTestCase(
        description=("diamond dependency B and C both from source then D joins them"),
        model_queries={
            "B": ('SELECT id, amount AS b_amount FROM __source("raw")'),
            "C": ('SELECT id, amount * 10 AS c_amount FROM __source("raw")'),
            "D": (
                "SELECT b.id, b.b_amount + c.c_amount AS total"
                ' FROM __ref("B") b'
                ' JOIN __ref("C") c ON b.id = c.id'
            ),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id, 5 AS amount",
        },
        helper_ctes={},
        expected_model_names=("B", "C", "D"),
        expected_cte_bodies={
            "B": "SELECT 1 AS id, 5 AS b_amount",
            "C": "SELECT 1 AS id, 50 AS c_amount",
            "D": "SELECT 1 AS id, 55 AS total",
        },
        expected_chain_length=3,
        expected_results={
            "B": ((1, 5),),
            "C": ((1, 50),),
            "D": ((1, 55),),
        },
    ),
    ExecuteChainTestCase(
        description=(
            "mixed inputs model joins chain predecessor with mock ref and produces correct result"
        ),
        model_queries={
            "stg_orders": ('SELECT id, amount FROM __source("raw")'),
            "enriched": (
                "SELECT o.id, o.amount, c.country"
                ' FROM __ref("stg_orders") o'
                ' JOIN __ref("countries") c'
                " ON o.id = c.id"
            ),
        },
        mock_ref_ctes={
            "countries": (
                "SELECT 1 AS id, 'US' AS country UNION ALL SELECT 2 AS id, 'UK' AS country"
            ),
        },
        mock_source_ctes={
            "raw": ("SELECT 1 AS id, 100 AS amount UNION ALL SELECT 2 AS id, 200 AS amount"),
        },
        helper_ctes={},
        expected_model_names=("stg_orders", "enriched"),
        expected_cte_bodies={
            "stg_orders": "SELECT 1 AS id, 100 AS amount",
            "enriched": "SELECT 1 AS id, 100 AS amount",
        },
        expected_chain_length=2,
        expected_results={
            "stg_orders": ((1, 100), (2, 200)),
            "enriched": ((1, 100, "US"), (2, 200, "UK")),
        },
    ),
    ExecuteChainTestCase(
        description="multi-row source propagates through chain",
        model_queries={
            "stg": 'SELECT id, val FROM __source("raw")',
            "agg": ('SELECT SUM(val) AS total FROM __ref("stg")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": (
                "SELECT 1 AS id, 10 AS val"
                " UNION ALL SELECT 2 AS id, 20 AS val"
                " UNION ALL SELECT 3 AS id, 30 AS val"
            ),
        },
        helper_ctes={},
        expected_model_names=("stg", "agg"),
        expected_cte_bodies={
            "stg": "SELECT 1 AS id, 10 AS val",
            "agg": "SELECT 60 AS total",
        },
        expected_chain_length=2,
        expected_results={
            "agg": ((60,),),
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXECUTE_CHAIN_TEST_CASES,
    ids=[case.description for case in EXECUTE_CHAIN_TEST_CASES],
)
def test_given_chain_when_executing_resolved_sql_then_produces_expected_rows(
    test_case: ExecuteChainTestCase,
    connection: Any,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    entry, _ = plan_test(test=compiled_test, project=project)

    assert len(entry.chain) == test_case.expected_chain_length

    step: ChainStep
    for step in entry.chain:
        expected_rows: tuple[tuple[object, ...], ...] | None = test_case.expected_results.get(
            step.model_name
        )
        result: Any = connection.execute(step.resolved_sql)
        rows: list[Any] = result.fetchall()
        actual: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in rows)
        assert expected_rows is None or actual == expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteMacroTestCase(
            description="macro test direct comparison executes through test runner",
            helper_ctes={"input_values": "SELECT '  PAID  ' AS raw_status"},
            actual_sql="SELECT LOWER(TRIM(raw_status)) AS status FROM input_values",
            expected_sql="SELECT 'paid' AS status",
            expected_rows=(("paid",),),
        )
    ],
    ids=["macro test direct comparison executes through test runner"],
)
def test_given_macro_test_plan_when_executing_then_it_passes_direct_comparison(
    test_case: ExecuteMacroTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("tests/unit/test_macro.sql"),
        relative_path=Path("tests/unit/test_macro.sql"),
        contents="",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=1,
        header_values={"mode": SqlTestMode.MACRO.value, "name": "normalizes status"},
        sql_body="",
        name="normalizes status",
        mode=SqlTestMode.MACRO,
    )
    helper_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        CompileSqlTestCte(name=name, sql_body=sql) for name, sql in test_case.helper_ctes.items()
    )
    sql_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="normalizes status",
        ),
        scope_deps=(CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        name="normalizes status",
        test_file=test_file,
        test_block=test_block,
        sql_body="",
        mode=SqlTestMode.MACRO,
        payload=CompiledDirectLogicSqlTestPayload(
            mode=SqlTestMode.MACRO,
            helper_ctes=helper_ctes,
            actual_cte=CompileSqlTestCte(
                name="__macro_actual__",
                sql_body=test_case.actual_sql,
            ),
            expected_cte=CompileSqlTestCte(
                name="__macro_expected__",
                sql_body=test_case.expected_sql,
            ),
            tested_resource_names=("normalize_status",),
        ),
    )

    entry, warnings = plan_test(
        test=sql_test,
        project=CompiledProject(
            run_id="test_run",
            effective_environment_name=None,
            effective_connection={},
            effective_vars={},
        ),
    )
    result: SqlTestExecutionResult = execute_sql_test(
        test_entry=entry, adapter=adapter, connection=connection
    )

    assert warnings == ()
    assert entry.chain[0].model_name == "macro normalizes status"
    rows: list[Any] = connection.execute(entry.chain[0].resolved_sql).fetchall()
    assert tuple(tuple(row) for row in rows) == test_case.expected_rows
    assert result.outcome == SqlTestOutcome.PASS
    assert result.step_results[0].model_name == "macro normalizes status"


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteChainTestCase(
            description="sqlglot path produces executable planned chain step sql",
            model_queries={
                "stg_orders": 'SELECT id, amount FROM __source("raw")',
                "fact_orders": (
                    "WITH local_helper AS (SELECT 1 AS one) "
                    "SELECT id, amount + one AS adjusted "
                    'FROM __ref("stg_orders") CROSS JOIN local_helper'
                ),
            },
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id, 100 AS amount"},
            helper_ctes={},
            expected_model_names=("stg_orders", "fact_orders"),
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id, 100 AS amount",
                "fact_orders": "SELECT 1 AS id, 101 AS adjusted",
            },
            expected_chain_length=2,
            expected_results={
                "stg_orders": ((1, 100),),
                "fact_orders": ((1, 101),),
            },
        )
    ],
    ids=["sqlglot path produces executable planned chain step sql"],
)
def test_given_sqlglot_enabled_when_planning_chain_then_step_sql_remains_executable(
    test_case: ExecuteChainTestCase,
    connection: Any,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    entry, _ = plan_test(test=compiled_test, project=project, sqlglot_enabled=True)

    assert len(entry.chain) == test_case.expected_chain_length

    step: ChainStep
    for step in entry.chain:
        assert "__REF(" not in step.resolved_sql
        assert "__SOURCE(" not in step.resolved_sql
        expected_rows: tuple[tuple[object, ...], ...] | None = test_case.expected_results.get(
            step.model_name
        )
        result: Any = connection.execute(step.resolved_sql)
        rows: list[Any] = result.fetchall()
        actual: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in rows)
        assert expected_rows is None or actual == expected_rows
