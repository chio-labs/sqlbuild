"""Compile star projections over PIVOT and UNPIVOT sources against DuckDB results."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pytest

from sqlbuild.compiler.compile.models import CompiledLineageColumnFact
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    ReshapedStarIntegrationTestCase,
    ReshapedStarLineageIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    RESHAPED_STAR_UPSTREAM_MODELS,
    compile_reshaped_star_model,
    lineage_source_pairs,
)

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("(\w+)"\)')
_PIVOT_OVER_CTE_SQL: str = (
    "WITH pivot_input AS (SELECT customer_id, category, amount "
    'FROM __ref("staged_orders")) '
    "SELECT * FROM pivot_input PIVOT (MAX(amount) FOR category IN ('books', 'games'))"
)
_UNPIVOT_OVER_CTE_SQL: str = (
    'WITH wide AS (SELECT customer_id, books, games FROM __ref("wide_orders")) '
    "SELECT * FROM wide UNPIVOT (amount FOR category IN (books, games))"
)


@pytest.mark.parametrize(
    "test_case",
    (
        ReshapedStarIntegrationTestCase(
            description="pivot over cte",
            query_sql=_PIVOT_OVER_CTE_SQL,
            expected_columns=("customer_id", "books", "games"),
        ),
        ReshapedStarIntegrationTestCase(
            description="unpivot over cte",
            query_sql=_UNPIVOT_OVER_CTE_SQL,
            expected_columns=("customer_id", "category", "amount"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_star_over_reshaped_cte_when_compiling_then_columns_match_duckdb(
    test_case: ReshapedStarIntegrationTestCase,
    tmp_path: Path,
) -> None:
    project, model = compile_reshaped_star_model(
        project_dir=tmp_path, query_sql=test_case.query_sql
    )
    with duckdb.connect() as connection:
        for name, sql in RESHAPED_STAR_UPSTREAM_MODELS.items():
            connection.execute(f"CREATE TABLE {name} AS {sql}")
        duckdb_columns: tuple[str, ...] = tuple(
            column[0]
            for column in connection.execute(
                _REF_PATTERN.sub(r"\1", test_case.query_sql)
            ).description
        )

    assert project.diagnostics == ()
    assert duckdb_columns == test_case.expected_columns
    assert model.inferred_columns is not None
    assert tuple(column.name for column in model.inferred_columns) == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    (
        ReshapedStarLineageIntegrationTestCase(
            description="pivot over cte",
            query_sql=_PIVOT_OVER_CTE_SQL,
            expected_sources=(
                frozenset({("staged_orders", "customer_id")}),
                frozenset({("staged_orders", "amount")}),
                frozenset({("staged_orders", "amount")}),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_star_over_pivoted_cte_when_compiling_then_lineage_follows_pivot_inputs(
    test_case: ReshapedStarLineageIntegrationTestCase,
    tmp_path: Path,
) -> None:
    _project, model = compile_reshaped_star_model(
        project_dir=tmp_path, query_sql=test_case.query_sql
    )
    lineage: Sequence[CompiledLineageColumnFact] | None = model.fast_lineage_columns

    assert lineage is not None
    assert tuple(lineage_source_pairs(column) for column in lineage) == test_case.expected_sources
