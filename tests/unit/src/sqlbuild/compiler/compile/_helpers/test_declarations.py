from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, SqlHookEntry
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    CompileDeclarationsErrorTestCase,
    CompileDeclarationsTestCase,
    DeclarationFingerprintTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import compile_first_model

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false
"""


@pytest.mark.parametrize(
    "test_case",
    [
        CompileDeclarationsTestCase(
            description="public and private declarations",
            expected_query_sql="""SELECT
  'DELIVERY' AS fulfillment_method,
  3 AS priority,
  'OPEN' AS state,
  7 + 2 AS threshold,
  'O''Brien' AS source_name""",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_public_and_private_declarations_when_compiling_then_resolves_scopes_and_contracts(
    test_case: CompileDeclarationsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
            "enums/market/market.sql": """
ENUM (name fulfillment_method, members [DELIVERY, PICKUP]);
ENUM (name priority, members (LOW 1, HIGH 3));
""",
            "constants/market/thresholds.sql": """
CONSTANT (name min_items, value 7);
CONSTANT (name source_name, value "O'Brien");
""",
            "models/orders.sql": """
MODEL (
  contract enforced,
  pre_hooks [sql('SELECT @const("min_items") + @const("_offset")')],
  enums (
    _state [OPEN, CLOSED],
  ),
  constants (
    _offset 2,
  ),
  columns (
    fulfillment_method (type fulfillment_method),
    priority (type priority),
    state (type _state),
    threshold (type INTEGER),
    source_name (type VARCHAR),
  ),
);

SELECT
  @enum("fulfillment_method").DELIVERY AS fulfillment_method,
  @enum("priority").HIGH AS priority,
  @enum("_state").OPEN AS state,
  @const("min_items") + @const("_offset") AS threshold,
  @const("source_name") AS source_name
""",
            "functions/sql/add_threshold.sql": """
FUNCTION (
  arguments (value INTEGER),
  returns INTEGER,
);

value + @const("min_items")
""",
            "sources/inline.yml": """
sources:
  - name: inline_values
    expression: |
      SELECT @const("min_items") AS value
""",
            "tests/unit/orders.sql": """
TEST ();

WITH __ref__orders AS (
  SELECT @enum("fulfillment_method").DELIVERY AS fulfillment_method
),
__expected__orders AS (
  SELECT @enum("fulfillment_method").DELIVERY AS fulfillment_method
)
SELECT 1
""",
            "tests/scenarios/orders.sql": """
SCENARIO ();

WITH __ref__orders AS (
  SELECT @const("min_items") AS threshold
),
__expected__orders AS (
  SELECT @const("min_items") AS threshold
)
SELECT 1
""",
            "audits/orders.sql": """
AUDIT ();

SELECT * FROM __ref("orders") WHERE threshold < @const("min_items")
""",
        },
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered_inputs,
        run_id="test_run",
    )

    model_input: CompileModelInput = compile_inputs.model_inputs[0]
    assert model_input.schema_entry is not None
    assert model_input.query_sql == test_case.expected_query_sql
    assert tuple(compile_inputs.public_enums) == ("fulfillment_method", "priority")
    assert tuple(compile_inputs.public_constants) == ("min_items", "source_name")
    assert tuple(declaration.name for declaration in model_input.enum_declarations) == ("_state",)
    assert tuple(declaration.name for declaration in model_input.constant_declarations) == (
        "_offset",
    )
    assert tuple(model_input.enum_columns) == ("fulfillment_method", "priority", "state")
    assert model_input.config.values["pre_hooks"] == [SqlHookEntry(statement="SELECT 7 + 2")]
    assert tuple(column.type for column in model_input.schema_entry.columns) == (
        "VARCHAR",
        "INTEGER",
        "VARCHAR",
        "INTEGER",
        "VARCHAR",
    )
    actual_column_audits: list[tuple[str, ...]] = []
    for column in model_input.schema_entry.columns:
        actual_column_audits.append(tuple(audit.definition_name for audit in column.audits))
    assert tuple(actual_column_audits) == (
        ("accepted_values",),
        ("accepted_values",),
        ("accepted_values",),
        (),
        (),
    )
    assert tuple(audit.sql_body for audit in compile_inputs.audit_inputs) == (
        'SELECT * FROM __ref("orders") WHERE threshold < 7',
        'SELECT fulfillment_method\nFROM __ref("orders")\nWHERE fulfillment_method IS NOT NULL\n'
        "  AND fulfillment_method NOT IN ('DELIVERY', 'PICKUP')",
        'SELECT priority\nFROM __ref("orders")\nWHERE priority IS NOT NULL\n'
        "  AND priority NOT IN (1, 3)",
        'SELECT state\nFROM __ref("orders")\nWHERE state IS NOT NULL\n'
        "  AND state NOT IN ('OPEN', 'CLOSED')",
    )
    assert tuple(function.body_sql for function in compile_inputs.sql_function_inputs) == (
        "value + 7",
    )
    assert tuple(source.source_entry.expression for source in compile_inputs.source_inputs) == (
        "SELECT 7 AS value\n",
    )
    assert tuple(test.sql_body for test in compile_inputs.test_inputs) == (
        "WITH __ref__orders AS (\n  SELECT 'DELIVERY' AS fulfillment_method\n),\n"
        "__expected__orders AS (\n  SELECT 'DELIVERY' AS fulfillment_method\n)\nSELECT 1",
    )
    assert tuple(scenario.sql_body for scenario in compile_inputs.scenario_inputs) == (
        "WITH __ref__orders AS (\n  SELECT 7 AS threshold\n),\n"
        "__expected__orders AS (\n  SELECT 7 AS threshold\n)\nSELECT 1",
    )
    compiled_project: CompiledProject = assemble_project(
        inputs=compile_inputs,
        skip_column_inference=True,
    )
    compiled_model: CompiledModel = compiled_project.models[0]
    assert tuple(compiled_project.public_enums) == ("fulfillment_method", "priority")
    assert tuple(compiled_project.public_constants) == ("min_items", "source_name")
    assert tuple(compiled_model.enum_columns) == ("fulfillment_method", "priority", "state")
    identity_metadata: dict[str, object] = json.loads(
        build_model_version_identity_metadata_json(model=compiled_model)
    )
    assert identity_metadata["execution_signature"] == {
        "pre_hooks": ["SqlHookEntry(statement='SELECT 7 + 2')"],
        "contract": {
            "enforced": True,
            "columns": [
                {
                    "name": "fulfillment_method",
                    "type": "VARCHAR",
                    "nullable": None,
                    "enum": {
                        "name": "fulfillment_method",
                        "members": [
                            {"name": "DELIVERY", "value": "DELIVERY"},
                            {"name": "PICKUP", "value": "PICKUP"},
                        ],
                    },
                },
                {
                    "name": "priority",
                    "type": "INTEGER",
                    "nullable": None,
                    "enum": {
                        "name": "priority",
                        "members": [
                            {"name": "LOW", "value": 1},
                            {"name": "HIGH", "value": 3},
                        ],
                    },
                },
                {
                    "name": "state",
                    "type": "VARCHAR",
                    "nullable": None,
                    "enum": {
                        "name": "_state",
                        "members": [
                            {"name": "OPEN", "value": "OPEN"},
                            {"name": "CLOSED", "value": "CLOSED"},
                        ],
                    },
                },
                {"name": "threshold", "type": "INTEGER", "nullable": None},
                {"name": "source_name", "type": "VARCHAR", "nullable": None},
            ],
        },
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationFingerprintTestCase(
            description="constant value changes rendered query identity",
            declaration_path="constants/threshold.sql",
            initial_declaration="CONSTANT (name threshold, value 7);\n",
            changed_declaration="CONSTANT (name threshold, value 8);\n",
            model_sql='MODEL ();\nSELECT @const("threshold") AS threshold\n',
            expected_query_hash_changed=True,
            expected_metadata_changed=False,
        ),
        DeclarationFingerprintTestCase(
            description="enum members change enforced contract identity",
            declaration_path="enums/state.sql",
            initial_declaration="ENUM (name state, members [OPEN]);\n",
            changed_declaration="ENUM (name state, members [OPEN, CLOSED]);\n",
            model_sql="""
MODEL (
  contract enforced,
  columns (state (type state)),
);
SELECT 'OPEN' AS state
""",
            expected_query_hash_changed=False,
            expected_metadata_changed=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declaration_change_when_compiling_then_updates_dependent_identity(
    test_case: DeclarationFingerprintTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
            test_case.declaration_path: test_case.initial_declaration,
            "models/orders.sql": test_case.model_sql,
        },
    )
    initial_model: CompiledModel = compile_first_model(project_dir=tmp_path)

    write_repo_files(
        tmp_path,
        {test_case.declaration_path: test_case.changed_declaration},
    )
    changed_model: CompiledModel = compile_first_model(project_dir=tmp_path)

    query_hash_changed: bool = compute_query_hash(initial_model.query_sql) != compute_query_hash(
        changed_model.query_sql
    )
    metadata_changed: bool = build_model_version_identity_metadata_json(
        model=initial_model
    ) != build_model_version_identity_metadata_json(model=changed_model)
    assert query_hash_changed == test_case.expected_query_hash_changed
    assert metadata_changed == test_case.expected_metadata_changed


@pytest.mark.parametrize(
    "test_case",
    [
        CompileDeclarationsErrorTestCase(
            description="unknown enum member",
            repo_files={
                "enums/state.sql": "ENUM (name state, members [OPEN, CLOSED]);",
                "models/orders.sql": ('MODEL ();\nSELECT @enum("state").MISSING AS state\n'),
            },
            expected_error_fragment="Unknown member 'MISSING' for enum 'state'",
        ),
        CompileDeclarationsErrorTestCase(
            description="unknown constant",
            repo_files={
                "models/orders.sql": 'MODEL ();\nSELECT @const("missing") AS value\n',
            },
            expected_error_fragment="Unknown constant 'missing'",
        ),
        CompileDeclarationsErrorTestCase(
            description="foreign private constant",
            repo_files={
                "models/a.sql": "MODEL (constants (_limit 7));\nSELECT 1 AS value\n",
                "models/b.sql": 'MODEL ();\nSELECT @const("_limit") AS value\n',
            },
            expected_error_fragment="Unknown constant '_limit' in this model",
        ),
        CompileDeclarationsErrorTestCase(
            description="non-private model constant name",
            repo_files={
                "models/orders.sql": "MODEL (constants (limit 7));\nSELECT 1 AS value\n",
            },
            expected_error_fragment="model-local constant 'limit' must start with '_'",
        ),
        CompileDeclarationsErrorTestCase(
            description="duplicate public enum name",
            repo_files={
                "enums/one.sql": "ENUM (name state, members [OPEN]);",
                "enums/nested/two.sql": "ENUM (name state, members [CLOSED]);",
                "models/orders.sql": "MODEL ();\nSELECT 1 AS value\n",
            },
            expected_error_fragment="Duplicate public enum 'state'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_declaration_usage_when_compiling_then_raises_compile_error(
    test_case: CompileDeclarationsErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.repo_files,
    )
    with pytest.raises(
        (CompileInputError, DeclarationParseError),
        match=test_case.expected_error_fragment,
    ):
        discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
        build_compile_inputs(discovered_inputs=discovered_inputs, run_id="test_run")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
