from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompileProjectInputs,
    CompilerDiagnostic,
)
from sqlbuild.compiler.contracts.main.validate import evaluate_model_contracts
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest._helpers.model_nodes import build_model_node
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SourceLocation
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ModelSchemaCompilationTestCase,
    ModelSchemaContractDiagnosticTestCase,
    ModelSchemaCursorTestCase,
    ModelSchemaErrorTestCase,
    ModelSchemaIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import compile_first_model

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = true
sql_validation = true
"""


@pytest.mark.parametrize(
    "test_case",
    [
        ModelSchemaCompilationTestCase(
            description="inherited schemas with additive local columns",
            expected_schema_paths=(
                "schemas/orders/base.sql",
                "schemas/orders/observed.sql",
                "schemas/orders/sourced.sql",
            ),
            expected_exact_column_names=(
                "order_id",
                "status",
                "source",
                "observed_at",
                "quality_flag",
            ),
            expected_exact_column_types=(
                "INTEGER",
                "VARCHAR",
                "VARCHAR",
                "TIMESTAMP",
                "BOOLEAN",
            ),
            expected_superset_column_names=("order_id", "status", "local_note"),
            expected_superset_inferred_column_names=(
                "order_id",
                "status",
                "local_note",
                "extra_column",
            ),
            expected_exact_order_audit_names=("not_null", "unique"),
            expected_exact_order_audit_paths=(
                "schemas/orders/base.sql",
                "models/exact_orders.sql",
            ),
            expected_superset_order_audit_names=("not_null",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_inherited_model_schemas_when_compiling_then_attaches_resolved_contracts(
    test_case: ModelSchemaCompilationTestCase,
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
  columns (
    order_id (audits [not_null, unique]),
    quality_flag (type BOOLEAN, nullable false),
  ),
);
SELECT
  1::INTEGER AS order_id,
  'OPEN'::VARCHAR AS status,
  'feed'::VARCHAR AS source,
  CURRENT_TIMESTAMP::TIMESTAMP AS observed_at,
  TRUE::BOOLEAN AS quality_flag
""",
            "models/order_superset.sql": """
MODEL (
  materialized view,
  schema staging,
  model_schema order,
  contract none,
  columns (
    local_note (type VARCHAR),
  ),
);
SELECT
  1::INTEGER AS order_id,
  'OPEN'::VARCHAR AS status,
  'declared'::VARCHAR AS local_note,
  'local'::VARCHAR AS extra_column
""",
        },
    )

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    assert (
        tuple(str(schema_file.relative_path) for schema_file in discovered.model_schema_files)
        == test_case.expected_schema_paths
    )
    inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered,
        run_id="test_run",
    )
    project: CompiledProject = assemble_project(inputs=inputs)
    models: dict[str, CompiledModel] = {model.name: model for model in project.models}

    exact: CompiledModel = models["exact_orders"]
    assert exact.schema_entry is not None
    assert (
        tuple(column.name for column in exact.schema_entry.columns)
        == test_case.expected_exact_column_names
    )
    assert (
        tuple(column.type for column in exact.schema_entry.columns)
        == test_case.expected_exact_column_types
    )
    assert exact.destination.schema == "staging"
    assert "model_schema" not in exact.config.values
    assert exact.schema_entry.type_enforcement is True
    assert exact.schema_entry.description == "Exact order model"
    assert tuple(exact.enum_columns) == ("status",)
    exact_order_audits: tuple[SchemaAuditInstance, ...] = exact.schema_entry.columns[0].audits
    assert (
        tuple(audit.definition_name for audit in exact_order_audits)
        == test_case.expected_exact_order_audit_names
    )
    assert all(audit.location is not None for audit in exact_order_audits)
    exact_order_audit_paths: tuple[str, ...] = tuple(
        str(cast(SourceLocation, audit.location).path) for audit in exact_order_audits
    )
    assert exact_order_audit_paths == test_case.expected_exact_order_audit_paths
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
    assert (
        tuple(column.name for column in superset.schema_entry.columns)
        == test_case.expected_superset_column_names
    )
    assert (
        tuple(column.name for column in superset.inferred_columns or ())
        == test_case.expected_superset_inferred_column_names
    )
    assert (
        tuple(audit.definition_name for audit in superset.schema_entry.columns[0].audits)
        == test_case.expected_superset_order_audit_names
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
            {"name": "local_note", "type": "VARCHAR", "nullable": None},
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
    assert tuple(manifest_columns) == ("order_id", "status", "local_note")


@pytest.mark.parametrize(
    "test_case",
    [
        ModelSchemaContractDiagnosticTestCase(
            description="superset contract requires model-local declared columns",
            contract="none",
            projection="1::INTEGER AS order_id, 'OPEN'::VARCHAR AS status",
            expected_code="K001",
        ),
        ModelSchemaContractDiagnosticTestCase(
            description="exact contract rejects additional output columns",
            contract="enforced",
            projection=(
                "1::INTEGER AS order_id, 'OPEN'::VARCHAR AS status, "
                "'declared'::VARCHAR AS local_note, 1 AS extra_column"
            ),
            expected_code="K005",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_named_schema_contract_mismatch_when_validating_then_reports_expected_diagnostic(
    test_case: ModelSchemaContractDiagnosticTestCase,
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
MODEL (
  model_schema order,
  contract {test_case.contract},
  columns (local_note (type VARCHAR)),
);
SELECT {test_case.projection}
""",
        },
    )

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    project: CompiledProject = assemble_project(
        inputs=build_compile_inputs(discovered_inputs=discovered, run_id="test_run")
    )

    diagnostics: tuple[CompilerDiagnostic, ...] = evaluate_model_contracts(
        project=project, dialect="duckdb"
    ).diagnostics
    assert tuple(diagnostic.code for diagnostic in diagnostics) == (test_case.expected_code,)
    assert "named SCHEMA" in (diagnostics[0].help or "")


@pytest.mark.parametrize(
    "test_case",
    [
        ModelSchemaIdentityTestCase(
            description="parent type change affects superset identity",
            initial_type="INTEGER",
            changed_type="BIGINT",
            expected_identity_changed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parent_schema_type_change_when_fingerprinting_superset_then_identity_changes(
    test_case: ModelSchemaIdentityTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    repo_files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_FILE,
        "schemas/order.sql": f"""
SCHEMA (name order, columns (order_id (type {test_case.initial_type})));
SCHEMA (name sourced_order, extends order, columns (source (type VARCHAR)));
""",
        "models/orders.sql": """
MODEL (model_schema sourced_order, contract none);
SELECT 1 AS order_id, 'feed' AS source
""",
    }
    write_repo_files(tmp_path, repo_files)

    initial: CompiledModel = compile_first_model(project_dir=tmp_path)
    write_repo_files(
        tmp_path,
        repo_files
        | {
            "schemas/order.sql": f"""
SCHEMA (name order, columns (order_id (type {test_case.changed_type})));
SCHEMA (name sourced_order, extends order, columns (source (type VARCHAR)));
"""
        },
    )
    changed: CompiledModel = compile_first_model(project_dir=tmp_path)

    assert (
        build_model_version_identity_metadata_json(model=initial)
        != build_model_version_identity_metadata_json(model=changed)
    ) is test_case.expected_identity_changed


@pytest.mark.parametrize(
    "test_case",
    [
        ModelSchemaCursorTestCase(
            description="local cursor column extends named enforced contract",
            expected_column_names=("event_id", "observed_at"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_local_cursor_column_when_validating_named_contract_then_combined_shape_is_used(
    test_case: ModelSchemaCursorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
            "schemas/event.sql": "SCHEMA (name event, columns (event_id (type INTEGER)));",
            "models/events.sql": """
MODEL (
  materialized incremental,
  incremental_strategy append,
  cursor observed_at,
  cursor_type timestamp,
  cursor_grain second,
  model_schema event,
  columns (observed_at (type TIMESTAMP)),
  contract enforced,
);
SELECT 1::INTEGER AS event_id, CURRENT_TIMESTAMP::TIMESTAMP AS observed_at
""",
        },
    )

    model: CompiledModel = compile_first_model(project_dir=tmp_path)

    assert model.schema_entry is not None
    assert (
        tuple(column.name for column in model.schema_entry.columns)
        == test_case.expected_column_names
    )


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
            description="model-local inherited column type override",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": """
MODEL (model_schema order, columns (ID (type BIGINT)));
SELECT 1 AS id
""",
            },
            expected_error_fragment="cannot override type for named-schema column 'ID'",
        ),
        ModelSchemaErrorTestCase(
            description="model-local inherited column nullability override",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": """
MODEL (model_schema order, columns (id (nullable false)));
SELECT 1 AS id
""",
            },
            expected_error_fragment="cannot override nullable for named-schema column 'id'",
        ),
        ModelSchemaErrorTestCase(
            description="model-local inherited column description override",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": """
MODEL (model_schema order, columns (id (description "Local")));
SELECT 1 AS id
""",
            },
            expected_error_fragment="cannot override description for named-schema column 'id'",
        ),
        ModelSchemaErrorTestCase(
            description="model-local inherited column empty augmentation",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": "MODEL (model_schema order, columns (id ())); SELECT 1 AS id",
            },
            expected_error_fragment="redeclares named-schema column 'id'",
        ),
        ModelSchemaErrorTestCase(
            description="unknown model-local inherited column audit reports model owner",
            repo_files={
                "schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));",
                "models/orders.sql": """
MODEL (model_schema order, columns (id (audits [missing_audit])));
SELECT 1 AS id
""",
            },
            expected_error_fragment=(
                "models/orders.sql references unknown generic audit 'missing_audit'"
            ),
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
