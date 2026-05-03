from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.models import (
    ChainStep,
    PlanWarning,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from tests.unit.src.sqlbuild.compiler.planner.helpers.sql_test_assembly._test_types import (
    PlanTestChainTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.sql_test_assembly.helpers import (
    build_test_and_project,
)

PLAN_TEST_CASES: list[PlanTestChainTestCase] = [
    PlanTestChainTestCase(
        description="single model with mock ref replaces ref in sql",
        model_queries={
            "orders": 'SELECT id, amount FROM __ref("raw_orders")',
        },
        mock_ref_ctes={
            "raw_orders": "SELECT 1 AS id, 100 AS amount",
        },
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("orders",),
        expected_chain_length=1,
        expected_sql_fragments={
            "orders": "SELECT 1 AS id, 100 AS amount",
        },
        expected_cte_bodies={
            "orders": "SELECT 1 AS id, 100 AS amount",
        },
    ),
    PlanTestChainTestCase(
        description="single model with mock source replaces source in sql",
        model_queries={
            "stg_orders": 'SELECT id FROM __source("raw_orders")',
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw_orders": "SELECT 1 AS id",
        },
        helper_ctes={},
        expected_model_names=("stg_orders",),
        expected_chain_length=1,
        expected_sql_fragments={
            "stg_orders": "SELECT 1 AS id",
        },
        expected_cte_bodies={
            "stg_orders": "SELECT 1 AS id",
        },
    ),
    PlanTestChainTestCase(
        description="two model chain resolves in dependency order",
        model_queries={
            "stg_orders": 'SELECT id FROM __source("raw")',
            "fact_orders": ('SELECT id, 1 AS flag FROM __ref("stg_orders")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id",
        },
        helper_ctes={},
        expected_model_names=("stg_orders", "fact_orders"),
        expected_chain_length=2,
        expected_sql_fragments={
            "fact_orders": "SELECT 1 AS id",
        },
        expected_cte_bodies={
            "stg_orders": "SELECT 1 AS id",
            "fact_orders": "SELECT 1 AS id, 1 AS flag",
        },
    ),
    PlanTestChainTestCase(
        description="three model chain A to B to C",
        model_queries={
            "A": 'SELECT id FROM __source("raw")',
            "B": 'SELECT id, id * 2 AS doubled FROM __ref("A")',
            "C": ('SELECT id, doubled + 1 AS final FROM __ref("B")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id",
        },
        helper_ctes={},
        expected_model_names=("A", "B", "C"),
        expected_chain_length=3,
        expected_sql_fragments={
            "C": "doubled + 1 AS final",
        },
        expected_cte_bodies={
            "A": "SELECT 1 AS id",
            "B": "SELECT 1 AS id",
            "C": "SELECT 1 AS id",
        },
    ),
    PlanTestChainTestCase(
        description="helper ctes included in mock subquery",
        model_queries={
            "orders": 'SELECT id, amount FROM __ref("raw")',
        },
        mock_ref_ctes={
            "raw": "SELECT id, amount FROM gen_data",
        },
        mock_source_ctes={},
        helper_ctes={
            "gen_data": "SELECT 1 AS id, 100 AS amount",
        },
        expected_model_names=("orders",),
        expected_chain_length=1,
        expected_sql_fragments={
            "orders": "gen_data",
        },
        expected_cte_bodies={
            "orders": "SELECT 1 AS id, 100 AS amount",
        },
    ),
    PlanTestChainTestCase(
        description=("unreachable mock ref produces warning"),
        model_queries={
            "B": 'SELECT id FROM __ref("A")',
            "C": 'SELECT id FROM __ref("B")',
        },
        mock_ref_ctes={
            "A": "SELECT 1 AS id",
            "B": "SELECT 1 AS id",
        },
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("C",),
        expected_chain_length=1,
        expected_sql_fragments={
            "C": "SELECT 1 AS id",
        },
        expected_warning_count=1,
        expected_warning_severity=WarningSeverity.WARNING,
        expected_cte_bodies={
            "C": "SELECT 1 AS id",
        },
    ),
    PlanTestChainTestCase(
        description="missing expected model produces error warning",
        model_queries={},
        mock_ref_ctes={
            "raw": "SELECT 1 AS id",
        },
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("nonexistent",),
        expected_chain_length=0,
        expected_warning_count=2,
        expected_warning_severity=None,
        expected_cte_bodies={
            "nonexistent": "SELECT 1",
        },
    ),
    PlanTestChainTestCase(
        description="diamond dependency A to B and C both to D",
        model_queries={
            "B": 'SELECT id FROM __source("raw")',
            "C": 'SELECT id FROM __source("raw")',
            "D": ('SELECT b.id FROM __ref("B") b JOIN __ref("C") c ON b.id = c.id'),
        },
        mock_ref_ctes={},
        mock_source_ctes={
            "raw": "SELECT 1 AS id",
        },
        helper_ctes={},
        expected_model_names=("B", "C", "D"),
        expected_chain_length=3,
        expected_sql_fragments={
            "D": "SELECT 1 AS id",
        },
        expected_cte_bodies={
            "B": "SELECT 1 AS id",
            "C": "SELECT 1 AS id",
            "D": "SELECT 1 AS id",
        },
    ),
    PlanTestChainTestCase(
        description=("unresolved ref produces error warning"),
        model_queries={
            "orders": ('SELECT id FROM __ref("missing_model")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("orders",),
        expected_chain_length=1,
        expected_warning_count=1,
        expected_warning_severity=WarningSeverity.ERROR,
        expected_cte_bodies={
            "orders": "SELECT 1",
        },
    ),
    PlanTestChainTestCase(
        description=("unresolved source produces error warning"),
        model_queries={
            "orders": ('SELECT id FROM __source("missing_source")'),
        },
        mock_ref_ctes={},
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("orders",),
        expected_chain_length=1,
        expected_warning_count=1,
        expected_warning_severity=WarningSeverity.ERROR,
        expected_cte_bodies={
            "orders": "SELECT 1",
        },
    ),
    PlanTestChainTestCase(
        description=("model with both mock ref and chain ref resolves both"),
        model_queries={
            "stg": 'SELECT id FROM __source("raw")',
            "final": ('SELECT a.id FROM __ref("stg") a JOIN __ref("lookup") b ON a.id = b.id'),
        },
        mock_ref_ctes={
            "lookup": "SELECT 1 AS id, 'US' AS country",
        },
        mock_source_ctes={
            "raw": "SELECT 1 AS id",
        },
        helper_ctes={},
        expected_model_names=("stg", "final"),
        expected_chain_length=2,
        expected_sql_fragments={
            "final": "SELECT 1 AS id",
        },
        expected_warning_count=0,
        expected_cte_bodies={
            "stg": "SELECT 1 AS id",
            "final": "SELECT 1 AS id",
        },
    ),
    PlanTestChainTestCase(
        description=("multiple unresolved refs produce multiple errors"),
        model_queries={
            "orders": ('SELECT a.id FROM __ref("x") a JOIN __source("y") b ON a.id = b.id'),
        },
        mock_ref_ctes={},
        mock_source_ctes={},
        helper_ctes={},
        expected_model_names=("orders",),
        expected_chain_length=1,
        expected_warning_count=2,
        expected_warning_severity=WarningSeverity.ERROR,
        expected_cte_bodies={
            "orders": "SELECT 1",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_TEST_CASES,
    ids=[case.description for case in PLAN_TEST_CASES],
)
def test_given_test_and_project_when_planning_then_produces_expected_chain(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    warnings: tuple[PlanWarning, ...]
    entry, warnings = plan_test(test=compiled_test, project=project)

    assert len(entry.chain) == test_case.expected_chain_length

    model_name: str
    expected_fragment: str
    for model_name, expected_fragment in test_case.expected_sql_fragments.items():
        matching: list[ChainStep] = [s for s in entry.chain if s.model_name == model_name]
        assert len(matching) == 1
        assert expected_fragment in matching[0].resolved_sql

    assert len(warnings) == test_case.expected_warning_count
    expected_sev: WarningSeverity | None = test_case.expected_warning_severity
    actual_sevs: tuple[WarningSeverity, ...] = tuple(w.severity for w in warnings)
    assert (expected_sev is None) or all(s == expected_sev for s in actual_sevs)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanTestChainTestCase(
            description="sqlglot path lifts refs and sources into readable top-level ctes",
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
            expected_chain_length=2,
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id, 100 AS amount",
                "fact_orders": "SELECT 1 AS id, 101 AS adjusted",
            },
        )
    ],
    ids=["sqlglot path lifts refs and sources into readable top-level ctes"],
)
def test_given_sqlglot_enabled_when_planning_test_then_it_uses_top_level_generated_ctes(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    warnings: tuple[PlanWarning, ...]
    entry, warnings = plan_test(test=compiled_test, project=project, sqlglot_enabled=True)

    assert not warnings
    assert len(entry.chain) == test_case.expected_chain_length
    step_map: dict[str, ChainStep] = {step.model_name: step for step in entry.chain}
    assert (
        "WITH __source__raw AS (SELECT 1 AS id, 100 AS amount)"
        in step_map["stg_orders"].resolved_sql
    )
    assert "FROM __source__raw" in step_map["stg_orders"].resolved_sql
    assert (
        "WITH __source__raw AS (SELECT 1 AS id, 100 AS amount), "
        "__ref__stg_orders AS (SELECT id, amount FROM __source__raw)"
        in step_map["fact_orders"].resolved_sql
    )
    assert "__ref__stg_orders AS (WITH" not in step_map["fact_orders"].resolved_sql
    assert "local_helper AS (SELECT 1 AS one)" in step_map["fact_orders"].resolved_sql
    assert "FROM __ref__stg_orders CROSS JOIN local_helper" in step_map["fact_orders"].resolved_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PlanTestChainTestCase(
            description="sqlglot path errors on generated cte name collision",
            model_queries={
                "orders": 'WITH __source__raw AS (SELECT 9 AS id) SELECT id FROM __source("raw")',
            },
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id"},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_error_fragment="conflicts with the generated source CTE",
            expected_cte_bodies={"orders": "SELECT 1 AS id"},
        )
    ],
    ids=["sqlglot path errors on generated cte name collision"],
)
def test_given_sqlglot_enabled_when_generated_cte_name_conflicts_then_it_raises_clear_error(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    assert test_case.expected_error_fragment is not None
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        plan_test(test=compiled_test, project=project, sqlglot_enabled=True)
