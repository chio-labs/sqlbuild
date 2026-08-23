from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompileProjectInputs
from sqlbuild.compiler.contracts.main.validate import evaluate_model_contracts
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest._helpers.model_nodes import build_model_node
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ModelSchemaErrorTestCase,
)

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = true
sql_validation = true
"""


def test_given_inherited_model_schemas_when_compiling_then_attaches_resolved_contracts(
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
            "enums/order_status.sql": "ENUM (name order_status, members [OPEN, CLOSED]);",
            "schemas/orders/base.sql": """
SCHEMA (
  name order,
  description "Canonical order schema",
  columns (
    order_id (type INTEGER, nullable false, audits [not_null]),
    status (type order_status),
  ),
);
""",
            "schemas/orders/sourced.sql": """
SCHEMA (
  name sourced_order,
  extends order,
  columns (source (type VARCHAR, nullable false)),
);
""",
            "schemas/orders/observed.sql": """
SCHEMA (
  name observed_order,
  extends sourced_order,
  description "Observed order schema",
  columns (observed_at (type TIMESTAMP)),
);
""",
            "models/exact_orders.sql": """
MODEL (
  materialized view,
  schema staging,
  model_schema observed_order,
  contract enforced,
  description "Exact order model",
);
SELECT
  1::INTEGER AS order_id,
  'OPEN'::VARCHAR AS status,
  'feed'::VARCHAR AS source,
  CURRENT_TIMESTAMP::TIMESTAMP AS observed_at
""",
            "models/order_superset.sql": """
MODEL (
  materialized view,
  schema staging,
  model_schema order,
  contract none,
);
SELECT
  1::INTEGER AS order_id,
  'OPEN'::VARCHAR AS status,
  'local'::VARCHAR AS extra_column
""",
        },
    )

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    assert tuple(
        str(schema_file.relative_path) for schema_file in discovered.model_schema_files
    ) == (
        "schemas/orders/base.sql",
        "schemas/orders/observed.sql",
        "schemas/orders/sourced.sql",
    )
    inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered,
        run_id="test_run",
    )
    project: CompiledProject = assemble_project(inputs=inputs)
    models: dict[str, CompiledModel] = {model.name: model for model in project.models}

    exact: CompiledModel = models["exact_orders"]
    assert exact.schema_entry is not None
    assert tuple(column.name for column in exact.schema_entry.columns) == (
        "order_id",
        "status",
        "source",
        "observed_at",
    )
    assert tuple(column.type for column in exact.schema_entry.columns) == (
        "INTEGER",
        "VARCHAR",
        "VARCHAR",
        "TIMESTAMP",
    )
    assert exact.destination.schema == "staging"
    assert "model_schema" not in exact.config.values
    assert exact.schema_entry.type_enforcement is True
    assert exact.schema_entry.description == "Exact order model"
    assert tuple(exact.enum_columns) == ("status",)
    exact_identity: dict[str, object] = json.loads(
        build_model_version_identity_metadata_json(model=exact)
    )
    assert exact_identity["execution_signature"]["contract"]["columns"][2] == {
        "name": "source",
        "type": "VARCHAR",
        "nullable": False,
    }

    superset: CompiledModel = models["order_superset"]
    assert superset.schema_entry is not None
    assert superset.schema_entry.description == "Canonical order schema"
    assert tuple(column.name for column in superset.schema_entry.columns) == ("order_id", "status")
    assert tuple(column.name for column in superset.inferred_columns or ()) == (
        "order_id",
        "status",
        "extra_column",
    )
    superset_identity: dict[str, object] = json.loads(
        build_model_version_identity_metadata_json(model=superset)
    )
    assert superset_identity["execution_signature"]["contract"] == {
        "enforced": False,
        "columns": [
            {"name": "order_id", "type": "INTEGER", "nullable": False},
            {
                "name": "status",
                "type": "VARCHAR",
                "nullable": None,
                "enum": {
                    "name": "order_status",
                    "members": [
                        {"name": "OPEN", "value": "OPEN"},
                        {"name": "CLOSED", "value": "CLOSED"},
                    ],
                },
            },
        ],
    }
    assert evaluate_model_contracts(project=project, dialect="duckdb").diagnostics == ()
    manifest_node: dict[str, object] = build_model_node(
        model=superset,
        plan_entry=None,
        project_name="demo",
    )
    assert manifest_node["description"] == "Canonical order schema"
    manifest_columns: object = manifest_node["columns"]
    assert isinstance(manifest_columns, dict)
    assert tuple(manifest_columns) == ("order_id", "status")


@pytest.mark.parametrize(
    ("contract", "projection", "expected_code"),
    [
        pytest.param(
            "none",
            "1::INTEGER AS order_id",
            "K001",
            id="superset contract requires every named column",
        ),
        pytest.param(
            "enforced",
            "1::INTEGER AS order_id, 'OPEN'::VARCHAR AS status, 1 AS extra_column",
            "K005",
            id="exact contract rejects additional output columns",
        ),
    ],
)
def test_given_named_schema_contract_mismatch_when_validating_then_reports_expected_diagnostic(
    contract: str,
    projection: str,
    expected_code: str,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
            "schemas/order.sql": """
SCHEMA (
  name order,
  columns (
    order_id (type INTEGER),
    status (type VARCHAR),
  ),
);
""",
            "models/orders.sql": f"""
MODEL (model_schema order, contract {contract});
SELECT {projection}
""",
        },
    )

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    project: CompiledProject = assemble_project(
        inputs=build_compile_inputs(discovered_inputs=discovered, run_id="test_run")
    )

    diagnostics = evaluate_model_contracts(project=project, dialect="duckdb").diagnostics
    assert tuple(diagnostic.code for diagnostic in diagnostics) == (expected_code,)
    assert "named SCHEMA" in (diagnostics[0].help or "")


def test_given_parent_schema_type_change_when_fingerprinting_superset_then_identity_changes(
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    repo_files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_FILE,
        "schemas/order.sql": """
SCHEMA (name order, columns (order_id (type INTEGER)));
SCHEMA (name sourced_order, extends order, columns (source (type VARCHAR)));
""",
        "models/orders.sql": """
MODEL (model_schema sourced_order, contract none);
SELECT 1 AS order_id, 'feed' AS source
""",
    }
    write_repo_files(tmp_path, repo_files)

    initial: CompiledModel = _compile_first_model(tmp_path)
    write_repo_files(
        tmp_path,
        repo_files
        | {
            "schemas/order.sql": """
SCHEMA (name order, columns (order_id (type BIGINT)));
SCHEMA (name sourced_order, extends order, columns (source (type VARCHAR)));
"""
        },
    )
    changed: CompiledModel = _compile_first_model(tmp_path)

    assert build_model_version_identity_metadata_json(
        model=initial
    ) != build_model_version_identity_metadata_json(model=changed)


def _compile_first_model(project_dir: Path) -> CompiledModel:
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    project: CompiledProject = assemble_project(
        inputs=build_compile_inputs(discovered_inputs=discovered, run_id="test_run")
    )
    return project.models[0]


@pytest.mark.parametrize(
    "test_case",
    [
        ModelSchemaErrorTestCase(
            description="unknown model schema",
            repo_files={
                "models/orders.sql": "MODEL (model_schema missing); SELECT 1 AS id",
            },
            expected_error_fragment="unknown model_schema 'missing'",
        ),
        ModelSchemaErrorTestCase(
            description="inline and named columns",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": """
MODEL (model_schema order, columns (id (type INTEGER)));
SELECT 1 AS id
""",
            },
            expected_error_fragment="cannot declare both model_schema and columns",
        ),
        ModelSchemaErrorTestCase(
            description="unknown parent",
            repo_files={
                "schemas/order.sql": """
SCHEMA (name order, extends missing, columns (id (type INTEGER)));
""",
                "models/orders.sql": "MODEL (); SELECT 1 AS id",
            },
            expected_error_fragment="extends unknown schema 'missing'",
        ),
        ModelSchemaErrorTestCase(
            description="transitive inheritance cycle",
            repo_files={
                "schemas/order.sql": """
SCHEMA (name first, extends second, columns (first_id (type INTEGER)));
SCHEMA (name second, extends third, columns (second_id (type INTEGER)));
SCHEMA (name third, extends first, columns (third_id (type INTEGER)));
""",
                "models/orders.sql": "MODEL (); SELECT 1 AS id",
            },
            expected_error_fragment="first -> second -> third -> first",
        ),
        ModelSchemaErrorTestCase(
            description="case insensitive inherited duplicate",
            repo_files={
                "schemas/order.sql": """
SCHEMA (name base, columns (order_id (type INTEGER)));
SCHEMA (name child, extends base, columns (ORDER_ID (type INTEGER)));
""",
                "models/orders.sql": "MODEL (); SELECT 1 AS id",
            },
            expected_error_fragment="redeclares inherited column 'ORDER_ID'",
        ),
        ModelSchemaErrorTestCase(
            description="unknown inherited column audit reports schema owner",
            repo_files={
                "schemas/order.sql": """
SCHEMA (name order, columns (id (type INTEGER, audits [missing_audit])));
""",
                "models/orders.sql": """
MODEL (model_schema order);
SELECT 1 AS id
""",
            },
            expected_error_fragment=(
                "schemas/order.sql references unknown generic audit 'missing_audit'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_model_schema_when_compiling_then_fails_closed(
    test_case: ModelSchemaErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.repo_files,
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
        build_compile_inputs(discovered_inputs=discovered, run_id="test_run")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
