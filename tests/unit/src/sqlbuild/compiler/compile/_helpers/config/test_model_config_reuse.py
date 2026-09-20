from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile._helpers.attachment import core as attachment_core
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileModelConfig, CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    DUCKDB_COMPILE_ADAPTER_CONTEXT,
)


def _compile_with_config_build_count(
    *,
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[CompileProjectInputs, int]:
    build_count: int = 0
    original_build_model_config = attachment_core.build_model_config

    def counting_build_model_config(**kwargs: Any) -> CompileModelConfig:
        nonlocal build_count
        build_count += 1
        return original_build_model_config(**kwargs)

    monkeypatch.setattr(attachment_core, "build_model_config", counting_build_model_config)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return (
        build_compile_inputs(
            discovered_inputs=discovered_inputs,
            adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        ),
        build_count,
    )


def test_given_static_column_contracts_when_attaching_then_reuses_only_base_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
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

    compile_inputs, build_count = _compile_with_config_build_count(
        project_dir=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert build_count == 1
    assert tuple(
        (column.name, column.type, column.nullable, column.description)
        for model_input in compile_inputs.model_inputs
        for column in getattr(model_input.schema_entry, "columns", ())
    ) == (
        ("customer_id", "INTEGER", False, "Customer id"),
        ("order_id", "BIGINT", True, "Order id"),
    )
    assert all(
        model_input.config.time_travel_retention.desired_days == 14
        for model_input in compile_inputs.model_inputs
    )
    first_values = compile_inputs.model_inputs[0].config.values
    second_values = compile_inputs.model_inputs[1].config.values
    assert first_values is not second_values
    first_values["test_marker"] = "first"
    assert "test_marker" not in second_values


def test_given_templated_columns_when_attaching_then_resolves_each_model_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
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

    compile_inputs, build_count = _compile_with_config_build_count(
        project_dir=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert build_count == 2
    assert tuple(
        (column.type, column.description)
        for model_input in compile_inputs.model_inputs
        for column in getattr(model_input.schema_entry, "columns", ())
    ) == (
        ("INTEGER", "customers identifier"),
        ("INTEGER", "orders identifier"),
    )
