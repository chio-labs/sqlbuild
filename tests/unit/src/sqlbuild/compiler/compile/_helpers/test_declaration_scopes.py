from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileModelInput, CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
    SqlHookEntry,
)
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ScopedDeclarationCompileTestCase,
    ScopedDeclarationErrorTestCase,
    ScopedDeclarationSurfaceTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    DUCKDB_COMPILE_ADAPTER_CONTEXT,
    compile_project_inputs,
)

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false
"""


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationCompileTestCase(
            "global declaration",
            {"constants/value.sql": "CONSTANT (name value, value 1);"},
            "models/domain/child/orders.sql",
            'MODEL ();\nSELECT @const("value") AS value\n',
            "SELECT 1 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "inherited declaration",
            {"models/domain/_constants/value.sql": "CONSTANT (name value, value 2);"},
            "models/domain/child/orders.sql",
            'MODEL ();\nSELECT @const("value") AS value\n',
            "SELECT 2 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "all ancestor declarations",
            {
                "models/domain/_constants/parent.sql": "CONSTANT (name parent_value, value 2);",
                "models/domain/child/_constants/child.sql": (
                    "CONSTANT (name child_value, value 3);"
                ),
            },
            "models/domain/child/grandchild/orders.sql",
            ('MODEL ();\nSELECT @const("parent_value") + @const("child_value") AS value\n'),
            "SELECT 2 + 3 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "local declaration",
            {"models/domain/_local_constants/value.sql": "CONSTANT (name value, value 4);"},
            "models/domain/orders.sql",
            'MODEL ();\nSELECT @const("value") AS value\n',
            "SELECT 4 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "private declaration",
            {},
            "models/domain/orders.sql",
            'MODEL (constants (_value 5));\nSELECT @const("_value") AS value\n',
            "SELECT 5 AS value",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scoped_declaration_when_compiling_model_then_only_lexically_visible_values_expand(
    test_case: ScopedDeclarationCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE}
        | test_case.files
        | {test_case.model_path: test_case.model_sql},
    )

    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)

    assert inputs.model_inputs[0].query_sql == test_case.expected_sql
    assert inputs.scope_index.declarations


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationErrorTestCase(
            "sibling declaration",
            {
                "models/one/_constants/value.sql": "CONSTANT (name value, value 1);",
                "models/two/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
            ("known but inaccessible", "models/one/_constants/value.sql", "models/two/orders.sql"),
        ),
        ScopedDeclarationErrorTestCase(
            "descendant declaration",
            {
                "models/domain/child/_constants/value.sql": "CONSTANT (name value, value 1);",
                "models/domain/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
            ("known but inaccessible", "models/domain/child/_constants/value.sql"),
        ),
        ScopedDeclarationErrorTestCase(
            "unknown declaration",
            {"models/orders.sql": 'MODEL ();\nSELECT @const("missing") AS value'},
            ("Unknown constant 'missing'", "Visible constants: none"),
        ),
        ScopedDeclarationErrorTestCase(
            "model private does not export to test",
            {
                "models/orders.sql": "MODEL (constants (_value 1));\nSELECT 1 AS value",
                "tests/unit/orders.sql": (
                    'TEST ();\nWITH __expected__orders AS (SELECT @const("_value") AS value) '
                    "SELECT 1"
                ),
            },
            ("known but inaccessible", "models/orders.sql", "tests/unit/orders.sql"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_inaccessible_or_unknown_declaration_when_compiling_then_diagnostic_is_distinct(
    test_case: ScopedDeclarationErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    with pytest.raises(CompileInputError) as error:
        compile_project_inputs(project_dir=tmp_path)

    for fragment in test_case.expected_error_fragments:
        assert fragment in str(error.value)


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationSurfaceTestCase(
            "inline model hook",
            {
                "models/domain/_constants/value.sql": "CONSTANT (name value, value 11);",
                "models/domain/orders.sql": (
                    "MODEL (pre_hooks [inline_sql(\"SELECT @const('value')\")]);\nSELECT 1"
                ),
            },
            lambda inputs: (
                cast(list[SqlHookEntry], inputs.model_inputs[0].config.values["pre_hooks"])[
                    0
                ].statement
            ),
            "SELECT 11",
        ),
        ScopedDeclarationSurfaceTestCase(
            "named hook definition path",
            {
                "hooks/sql/domain/_constants/value.sql": "CONSTANT (name value, value 12);",
                "hooks/sql/domain/typed.sql": 'HOOK ();\nSELECT @const("value")',
                "models/orders.sql": 'MODEL (post_hooks [sql("typed")]);\nSELECT 1',
            },
            lambda inputs: (
                cast(list[SqlHookEntry], inputs.model_inputs[0].config.values["post_hooks"])[
                    0
                ].statement
            ),
            "SELECT 12",
        ),
        ScopedDeclarationSurfaceTestCase(
            "function definition path",
            {
                "functions/sql/domain/_constants/value.sql": "CONSTANT (name value, value 13);",
                "functions/sql/domain/value.sql": ('FUNCTION (returns INTEGER);\n@const("value")'),
                "models/orders.sql": "MODEL ();\nSELECT 1",
            },
            lambda inputs: inputs.sql_function_inputs[0].body_sql,
            "13",
        ),
        ScopedDeclarationSurfaceTestCase(
            "standalone audit definition path",
            {
                "audits/domain/_constants/value.sql": "CONSTANT (name value, value 15);",
                "audits/domain/check.sql": 'AUDIT ();\nSELECT @const("value")',
                "models/orders.sql": "MODEL ();\nSELECT 1",
            },
            lambda inputs: inputs.audit_inputs[0].sql_body,
            "SELECT 15",
        ),
        ScopedDeclarationSurfaceTestCase(
            "generic audit definition path",
            {
                "audits/generic/domain/_constants/value.sql": ("CONSTANT (name value, value 18);"),
                "audits/generic/domain/scoped.sql": (
                    'AUDIT ();\nSELECT * FROM __ref("@model") WHERE @const("value") = 18'
                ),
                "models/orders.sql": "MODEL (audits [scoped]);\nSELECT 1",
            },
            lambda inputs: inputs.audit_inputs[0].sql_body,
            'SELECT * FROM __ref("orders") WHERE 18 = 18',
        ),
        ScopedDeclarationSurfaceTestCase(
            "unit test authored path",
            {
                "tests/unit/domain/_constants/value.sql": "CONSTANT (name value, value 16);",
                "tests/unit/domain/orders.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    '__expected__orders AS (SELECT @const("value") AS value) SELECT 1'
                ),
                "models/orders.sql": "MODEL ();\nSELECT 1 AS value",
            },
            lambda inputs: inputs.test_inputs[0].sql_body,
            "WITH __ref__orders AS (SELECT 1 AS value), "
            "__expected__orders AS (SELECT 16 AS value) SELECT 1",
        ),
        ScopedDeclarationSurfaceTestCase(
            "scenario authored path",
            {
                "tests/scenarios/domain/_constants/value.sql": ("CONSTANT (name value, value 17);"),
                "tests/scenarios/domain/orders.sql": (
                    "SCENARIO ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    '__expected__orders AS (SELECT @const("value") AS value) SELECT 1'
                ),
                "models/orders.sql": "MODEL ();\nSELECT 1 AS value",
            },
            lambda inputs: inputs.scenario_inputs[0].sql_body,
            "WITH __ref__orders AS (SELECT 1 AS value), "
            "__expected__orders AS (SELECT 17 AS value) SELECT 1",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scoped_declaration_when_compiling_sql_surface_then_uses_authored_definition_path(
    test_case: ScopedDeclarationSurfaceTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    actual: str | None = test_case.result(inputs)

    assert actual == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationCompileTestCase(
            description="inherited enum contract",
            files={"models/domain/_enums/state.sql": "ENUM (name state, members [OPEN, CLOSED]);"},
            model_path="models/domain/child/orders.sql",
            model_sql=(
                "MODEL (contract enforced, columns (state (type state)));\n"
                'SELECT @enum("state").OPEN AS state'
            ),
            expected_sql="SELECT 'OPEN' AS state",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_inherited_enum_when_compiling_contract_then_resolves_from_model_path(
    test_case: ScopedDeclarationCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT_FILE,
        }
        | test_case.files
        | {test_case.model_path: test_case.model_sql},
    )

    model: CompileModelInput = compile_project_inputs(project_dir=tmp_path).model_inputs[0]

    assert model.query_sql == test_case.expected_sql
    assert model.schema_entry is not None
    assert model.schema_entry.columns[0].type == "VARCHAR"
    assert tuple(model.enum_columns) == ("state",)


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationCompileTestCase(
            description="source authored path",
            files={
                "sources/domain/_constants/value.sql": "CONSTANT (name value, value 14);",
                "models/orders.sql": "MODEL ();\nSELECT 1",
            },
            model_path="sources/domain/source.yml",
            model_sql='SELECT @const("value")',
            expected_sql="SELECT 14",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scoped_declaration_when_compiling_source_then_uses_authored_source_path(
    test_case: ScopedDeclarationCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)
    source_path: Path = tmp_path / test_case.model_path
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    discovered = replace(
        discovered,
        source_files=(
            DiscoveredSourceFile(
                file_path=source_path,
                relative_path=Path(test_case.model_path),
                contents="",
                source_entries=(SourceEntry(name="raw", expression=test_case.model_sql),),
            ),
        ),
    )

    inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered,
        adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        run_id="source_scope_test",
    )

    assert inputs.source_inputs[0].source_entry.expression == test_case.expected_sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
