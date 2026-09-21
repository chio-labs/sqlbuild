from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.unit.src.sqlbuild.compiler.compile._helpers.config._test_types import (
    ExpectedCountTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.config.helpers import (
    compile_input_schema_columns,
    compile_with_config_build_count,
)


@pytest.mark.parametrize(
    "test_case",
    [ExpectedCountTestCase(description="static configuration is reused", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_static_column_contracts_when_attaching_then_reuses_only_base_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    test_case: ExpectedCountTestCase,
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false

[defaults]
materialized = "table"
contract = "enforced"

[materialization_defaults.table]
time_travel_retention = "14d"
""".strip()
            + "\n",
            "models/customers.sql": """
MODEL (
  columns (customer_id (type INTEGER, nullable false, description "Customer id")),
);

SELECT 1 AS customer_id
""".strip()
            + "\n",
            "models/orders.sql": """
MODEL (
  columns (order_id (type BIGINT, nullable true, description "Order id")),
);

SELECT 1 AS order_id
""".strip()
            + "\n",
        },
    )

    compile_inputs, build_count = compile_with_config_build_count(
        project_dir=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert build_count == test_case.expected_count
    assert tuple(
        (column.name, column.type, column.nullable, column.description)
        for column in compile_input_schema_columns(compile_inputs)
    ) == (
        ("customer_id", "INTEGER", False, "Customer id"),
        ("order_id", "BIGINT", True, "Order id"),
    )
    assert all(
        model_input.config.time_travel_retention.desired_days == 14
        for model_input in compile_inputs.model_inputs
    )
    first_values: dict[str, object] = compile_inputs.model_inputs[0].config.values
    second_values: dict[str, object] = compile_inputs.model_inputs[1].config.values
    assert first_values is not second_values
    first_values["test_marker"] = "first"
    assert "test_marker" not in second_values


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedCountTestCase(
            description="templated configurations remain distinct", expected_count=2
        )
    ],
    ids=lambda case: case.description,
)
def test_given_templated_columns_when_attaching_then_resolves_each_model_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    test_case: ExpectedCountTestCase,
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false

[vars]
identifier_type = "INTEGER"
""".strip()
            + "\n",
            "models/customers.sql": """
MODEL (
  columns (
    customer_id (
      type ${identifier_type},
      description "${CTX:model.name} identifier",
    )
  ),
);

SELECT 1 AS customer_id
""".strip()
            + "\n",
            "models/orders.sql": """
MODEL (
  columns (
    order_id (
      type ${identifier_type},
      description "${CTX:model.name} identifier",
    )
  ),
);

SELECT 1 AS order_id
""".strip()
            + "\n",
        },
    )

    compile_inputs, build_count = compile_with_config_build_count(
        project_dir=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert build_count == test_case.expected_count
    assert tuple(
        (column.type, column.description) for column in compile_input_schema_columns(compile_inputs)
    ) == (
        ("INTEGER", "customers identifier"),
        ("INTEGER", "orders identifier"),
    )
