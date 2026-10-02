"""Set operations after subquery operands combine the outer queries through the real CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    SetOperationArityMismatchTestCase,
    SetOperationLifecycleTestCase,
    SetOperationModel,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    SetOperationCompileResult,
    SetOperationLifecycleResult,
    compile_set_operation_project,
    run_set_operation_lifecycle,
    write_set_operation_project,
)

_INPUTS: str = (
    "WITH orders AS (\n"
    "  SELECT * FROM (VALUES (1, 20), (2, 5)) AS v(order_id, amount)\n"
    "), limits AS (SELECT 10 AS max_amount)\n"
)
_ALL_ORDERS: str = "SELECT o.order_id, o.amount FROM orders AS o"


@pytest.mark.parametrize(
    "test_case",
    [
        SetOperationLifecycleTestCase(
            description="subquery operands before set operations",
            models=(
                SetOperationModel(
                    description="scalar subquery in WHERE before UNION ALL",
                    name="where_scalar_union_all",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount < (SELECT l.max_amount FROM limits AS l)\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="scalar subquery in WHERE before EXCEPT",
                    name="where_scalar_except",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount > (SELECT l.max_amount FROM limits AS l)\n"
                        f"EXCEPT\n{_ALL_ORDERS} WHERE o.order_id = 2"
                    ),
                    expected_row_count=1,
                ),
                SetOperationModel(
                    description="scalar subquery in WHERE before INTERSECT",
                    name="where_scalar_intersect",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount > (SELECT l.max_amount FROM limits AS l)\n"
                        f"INTERSECT\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=1,
                ),
                SetOperationModel(
                    description="IN subquery before UNION ALL",
                    name="where_in_union_all",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount IN (SELECT l.max_amount * 2 FROM limits AS l)\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="correlated EXISTS before UNION ALL",
                    name="where_exists_union_all",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE EXISTS (SELECT 1 FROM limits AS l WHERE l.max_amount > o.amount)\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="nested scalar subqueries before UNION ALL",
                    name="where_nested_scalar_union_all",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount < (\n"
                        "  SELECT MAX(l.max_amount) FROM limits AS l\n"
                        "  WHERE l.max_amount > (SELECT MIN(o2.amount) FROM orders AS o2)\n"
                        ")\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="scalar subquery in HAVING before UNION ALL",
                    name="having_scalar_union_all",
                    query_sql=(
                        f"{_INPUTS}SELECT o.order_id, SUM(o.amount) AS amount FROM orders AS o\n"
                        "GROUP BY o.order_id\n"
                        "HAVING SUM(o.amount) > (SELECT l.max_amount FROM limits AS l)\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="scalar subquery in JOIN ON before UNION ALL",
                    name="join_on_scalar_union_all",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "JOIN limits AS l\n"
                        "  ON o.amount > (SELECT MIN(l2.max_amount) FROM limits AS l2)\n"
                        f"UNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=3,
                ),
                SetOperationModel(
                    description="scalar subquery in SELECT list before UNION ALL",
                    name="select_list_scalar_union_all",
                    query_sql=(
                        f"{_INPUTS}SELECT o.order_id, "
                        "(SELECT l.max_amount FROM limits AS l) AS amount\n"
                        f"FROM orders AS o\nUNION ALL\n{_ALL_ORDERS}"
                    ),
                    expected_row_count=4,
                ),
                SetOperationModel(
                    description="parenthesized branches around a scalar subquery",
                    name="parenthesized_branches_union_all",
                    query_sql=(
                        f"{_INPUTS}({_ALL_ORDERS}\n"
                        "WHERE o.amount < (SELECT l.max_amount FROM limits AS l))\n"
                        f"UNION ALL\n({_ALL_ORDERS})"
                    ),
                    expected_row_count=3,
                ),
            ),
            expected_column_count=2,
            expected_diagnostics=(),
            expected_rule_summary="10 models evaluated, 0 findings",
            expected_indented_set_operation_lines=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_set_operation_after_subquery_operand_when_compiling_building_and_formatting_then_outer_queries_combine(
    test_case: SetOperationLifecycleTestCase,
    tmp_path: Path,
) -> None:
    result: SetOperationLifecycleResult = run_set_operation_lifecycle(
        project_dir=tmp_path / "orders_project", models=test_case.models
    )
    expected_column_counts: dict[str, int] = {
        model.name: test_case.expected_column_count for model in test_case.models
    }

    assert result.compiled.exit_code == 0, result.compiled.output
    assert result.compiled.diagnostics == test_case.expected_diagnostics
    assert result.compiled.column_counts == expected_column_counts
    assert result.build.returncode == 0, result.build.stdout + result.build.stderr
    assert result.relation_shapes == {
        model.name: (test_case.expected_column_count, model.expected_row_count)
        for model in test_case.models
    }
    assert result.rules.returncode == 0, result.rules.stdout + result.rules.stderr
    assert test_case.expected_rule_summary in result.rules.stdout + result.rules.stderr
    assert result.format.returncode == 0, result.format.stdout + result.format.stderr
    assert result.indented_set_operation_lines == test_case.expected_indented_set_operation_lines
    assert result.recompiled.exit_code == 0, result.recompiled.output
    assert result.recompiled.diagnostics == test_case.expected_diagnostics
    assert result.recompiled.column_counts == expected_column_counts


@pytest.mark.parametrize(
    "test_case",
    [
        SetOperationArityMismatchTestCase(
            description="outer branch drops a column after a scalar subquery predicate",
            models=(
                SetOperationModel(
                    description="outer branch drops a column",
                    name="mismatched_branches",
                    query_sql=(
                        f"{_INPUTS}{_ALL_ORDERS}\n"
                        "WHERE o.amount < (SELECT l.max_amount FROM limits AS l)\n"
                        "UNION ALL\nSELECT o.order_id FROM orders AS o"
                    ),
                ),
            ),
            expected_exit_code=1,
            expected_diagnostics=(
                ("B216", "UNION operands return different column counts: left 2, right 1"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_outer_branch_after_subquery_operand_when_compiling_then_b216_reports_outer_counts(
    test_case: SetOperationArityMismatchTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "orders_project"
    write_set_operation_project(project_dir=project_dir, models=test_case.models)

    result: SetOperationCompileResult = compile_set_operation_project(project_dir=project_dir)

    assert result.exit_code == test_case.expected_exit_code, result.output
    assert result.diagnostics == test_case.expected_diagnostics


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
