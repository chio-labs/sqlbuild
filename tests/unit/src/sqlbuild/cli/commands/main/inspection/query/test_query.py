from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from sqlbuild.cli.commands.exceptions import QueryExecutionError
from sqlbuild.cli.commands.main.inspection._query import run_query
from tests.unit.src.sqlbuild.cli.commands.main.inspection.query._test_types import (
    QueryExecutionErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryExecutionErrorTestCase(
            description="missing relation",
            sql="SELECT * FROM missing_orders",
            expected_message_fragment="Table with name missing_orders does not exist",
        ),
        QueryExecutionErrorTestCase(
            description="syntax error",
            sql="SELECT FROM WHERE",
            expected_message_fragment="syntax error",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_rejects_query_when_running_query_then_raises_cli_error(
    test_case: QueryExecutionErrorTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n',
        encoding="utf-8",
    )

    with pytest.raises(QueryExecutionError) as raised:
        run_query(project_dir=tmp_path, sql=test_case.sql)

    assert raised.value.code == test_case.expected_code
    assert raised.value.exit_code == test_case.expected_exit_code
    assert test_case.expected_message_fragment in raised.value.message
    assert isinstance(raised.value.__cause__, duckdb.Error)
