from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._assemble_project import assemble_project
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
    SqlHookEntry,
)
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    UsageKind,
)
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpectedModelDeclarationGrantTestCase,
    RelationshipUsageTestCase,
    ScopedDeclarationCompileTestCase,
    ScopedDeclarationErrorTestCase,
    ScopedDeclarationSurfaceTestCase,
    ScopePlacementCompileTestCase,
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
            {"models/domain/constants/value.sql": "CONSTANT (name value, value 2);"},
            "models/domain/child/orders.sql",
            'MODEL ();\nSELECT @const("value") AS value\n',
            "SELECT 2 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "all ancestor declarations",
            {
                "models/domain/constants/parent.sql": "CONSTANT (name parent_value, value 2);",
                "models/domain/child/constants/child.sql": (
                    "CONSTANT (name child_value, value 3);"
                ),
            },
            "models/domain/child/grandchild/orders.sql",
            ('MODEL ();\nSELECT @const("parent_value") + @const("child_value") AS value\n'),
            "SELECT 2 + 3 AS value",
        ),
        ScopedDeclarationCompileTestCase(
            "local declaration",
            {"models/domain/_constants/value.sql": "CONSTANT (name value, value 4);"},
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
        ScopedDeclarationErrorTestCase(
            "filename resemblance without expected relationship",
            {
                "models/domain/_constants/value.sql": "CONSTANT (name model_value, value 9);",
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/unit/orders.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__assert__valid AS (SELECT @const('model_value') WHERE FALSE) SELECT 1"
                ),
            },
            ("known but inaccessible", "models/domain/_constants/value.sql"),
        ),
        ScopedDeclarationErrorTestCase(
            "unrelated production scope is not granted",
            {
                "models/orders/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "models/customers/_constants/value.sql": (
                    "CONSTANT (name customer_value, value 10);"
                ),
                "models/customers/customers.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS (SELECT @const('customer_value') AS value) SELECT 1"
                ),
            },
            ("known but inaccessible", "models/customers/_constants/value.sql"),
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
        ExpectedModelDeclarationGrantTestCase(
            description="single model inherited local constant and enum",
            files={
                "models/domain/_constants/inherited.sql": (
                    "CONSTANT (name inherited_value, value 2);"
                ),
                "models/domain/_constants/local.sql": ("CONSTANT (name local_value, value 3);"),
                "models/domain/_enums/state.sql": "ENUM (name state, members [OPEN, CLOSED]);",
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value, 'OPEN' AS state",
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS (SELECT @const('inherited_value') + "
                    "@const('local_value') AS value, @enum('state').OPEN AS state) SELECT 1"
                ),
            },
            expected_sql_fragments=("SELECT 2 + 3 AS value", "'OPEN' AS state"),
            expected_grants=(
                ("constant:inherited_value", "model:orders", "test:check"),
                ("constant:local_value", "model:orders", "test:check"),
                ("enum:state", "model:orders", "test:check"),
            ),
        ),
        ExpectedModelDeclarationGrantTestCase(
            description="multiple expected models deterministic union",
            files={
                "models/a/_constants/a.sql": "CONSTANT (name a_value, value 4);",
                "models/a/a.sql": "MODEL ();\nSELECT 4 AS value",
                "models/b/_constants/b.sql": "CONSTANT (name b_value, value 5);",
                "models/b/b.sql": "MODEL ();\nSELECT 5 AS value",
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__a AS (SELECT 1 AS value), "
                    "__expected__b AS (SELECT @const('b_value') AS value), "
                    "__expected__a AS (SELECT @const('a_value') AS value) SELECT 1"
                ),
            },
            expected_sql_fragments=("SELECT 5 AS value", "SELECT 4 AS value"),
            expected_grants=(
                ("constant:a_value", "model:a", "test:check"),
                ("constant:b_value", "model:b", "test:check"),
            ),
        ),
        ExpectedModelDeclarationGrantTestCase(
            description="test path visibility remains separate from model grant",
            files={
                "models/domain/_constants/model.sql": "CONSTANT (name model_value, value 6);",
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/unit/_constants/test.sql": "CONSTANT (name test_value, value 7);",
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS (SELECT @const('model_value') + "
                    "@const('test_value') AS value) SELECT 1"
                ),
            },
            expected_sql_fragments=("SELECT 6 + 7 AS value",),
            expected_grants=(("constant:model_value", "model:orders", "test:check"),),
        ),
        ExpectedModelDeclarationGrantTestCase(
            description="model private declaration is not granted",
            files={
                "models/orders.sql": (
                    "MODEL (constants (_private 8));\nSELECT @const('_private') AS value"
                ),
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS (SELECT 1 AS value) SELECT 1"
                ),
            },
            expected_sql_fragments=("SELECT 1 AS value",),
            expected_grants=(),
        ),
        ExpectedModelDeclarationGrantTestCase(
            description="filename resemblance and no expected model grant nothing",
            files={
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/unit/orders.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__assert__valid AS (SELECT 1 WHERE FALSE) SELECT 1"
                ),
            },
            expected_sql_fragments=("__assert__valid",),
            expected_grants=(),
        ),
        ExpectedModelDeclarationGrantTestCase(
            description="scenario expected model grant",
            files={
                "models/domain/_constants/value.sql": "CONSTANT (name scenario_value, value 10);",
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/scenarios/check.sql": (
                    "SCENARIO ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS (SELECT @const('scenario_value') AS value) SELECT 1"
                ),
            },
            expected_sql_fragments=("SELECT 10 AS value",),
            expected_grants=(("constant:scenario_value", "model:orders", "scenario:check"),),
            input_collection="scenario_inputs",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_expected_models_when_compiling_then_public_declarations_are_granted_with_provenance(
    test_case: ExpectedModelDeclarationGrantTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    first: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    second: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    compiled: CompiledProject = assemble_project(inputs=first, skip_column_inference=True)
    sql_body: str = getattr(first, test_case.input_collection)[0].sql_body
    grants: tuple[tuple[str, str, str], ...] = tuple(
        sorted(
            (
                f"{grant.declaration.kind.value}:{grant.declaration.name}",
                f"{grant.through.kind.value}:{grant.through.name}",
                f"{grant.resource.kind.value}:{grant.resource.name}",
            )
            for grant in first.scope_index.grants
        )
    )

    assert all(fragment in sql_body for fragment in test_case.expected_sql_fragments)
    assert grants == test_case.expected_grants
    assert first.scope_index.completeness.relationships
    assert first.scope_index == second.scope_index
    assert scope_metadata_projection(index=first.scope_index) == scope_metadata_projection(
        index=second.scope_index
    )
    assert compiled.scope_index.grants == first.scope_index.grants


@pytest.mark.parametrize(
    "test_case",
    (
        RelationshipUsageTestCase(
            description="expected model provenance is retained",
            files={
                "models/domain/_constants/value.sql": ("CONSTANT (name model_value, value 6);"),
                "models/domain/orders.sql": "MODEL ();\nSELECT 1 AS value",
                "tests/unit/check.sql": (
                    "TEST ();\nWITH __ref__orders AS (SELECT 1 AS value), "
                    "__expected__orders AS "
                    "(SELECT @const('model_value') AS value) SELECT 1"
                ),
            },
            expected_usage=UsageRecord(
                consumer=ResourceIdentity(ResourceKind.TEST, "check"),
                declaration=DeclarationIdentity(DeclarationKind.CONSTANT, "model_value"),
                kind=UsageKind.RUNTIME,
                through=ResourceIdentity(ResourceKind.MODEL, "orders"),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relationship_granted_reference_when_compiling_then_usage_retains_model_provenance(
    test_case: RelationshipUsageTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files,
    )

    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    compiled: CompiledProject = assemble_project(inputs=inputs, skip_column_inference=True)

    assert test_case.expected_usage in compiled.scope_index.usages


@pytest.mark.parametrize(
    "test_case",
    (
        ScopePlacementCompileTestCase(
            description="exact local placement is accepted",
            files={
                "models/domain/_constants/value.sql": ("CONSTANT (name value, value 1);"),
                "models/domain/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
        ),
        ScopePlacementCompileTestCase(
            description="inherited lowest common ancestor is accepted",
            files={
                "models/domain/constants/value.sql": "CONSTANT (name value, value 1);",
                "models/domain/a/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
                "models/domain/b/customers.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_exact_declaration_placement_when_assembling_then_project_is_accepted(
    test_case: ScopePlacementCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files,
    )

    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    compiled: CompiledProject = assemble_project(inputs=inputs, skip_column_inference=True)

    assert compiled.scope_index.completeness.runtime_usage is test_case.expected_complete
    assert compiled.scope_index.completeness.placement is test_case.expected_complete


@pytest.mark.parametrize(
    "test_case",
    (
        ScopePlacementCompileTestCase(
            description="used global with one owner is rejected as over broad",
            files={
                "constants/value.sql": "CONSTANT (name value, value 1);",
                "models/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
            expected_fragment="required exact-owner-private at 'models'",
        ),
        ScopePlacementCompileTestCase(
            description="unused global is rejected",
            files={
                "constants/value.sql": "CONSTANT (name value, value 1);",
                "models/orders.sql": "MODEL ();\nSELECT 1 AS value",
            },
            expected_fragment="Unused global declaration 'constant:value'",
        ),
        ScopePlacementCompileTestCase(
            description="unused private is rejected",
            files={
                "models/orders.sql": ("MODEL (constants (_value 1));\nSELECT 1 AS value"),
            },
            expected_fragment="Unused private declaration 'constant:model:orders._value'",
        ),
        ScopePlacementCompileTestCase(
            description="inherited declaration used in one directory must be local",
            files={
                "models/domain/constants/value.sql": "CONSTANT (name value, value 1);",
                "models/domain/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
            expected_fragment="required exact-owner-private at 'models/domain'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_declaration_placement_when_assembling_then_project_is_rejected(
    test_case: ScopePlacementCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files,
    )
    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)

    with pytest.raises(CompileInputError, match=cast(str, test_case.expected_fragment)):
        _ = assemble_project(inputs=inputs, skip_column_inference=True)


@pytest.mark.parametrize(
    "test_case",
    (
        ScopePlacementCompileTestCase(
            description="over broad global is advisory when placement enforcement is disabled",
            files={
                "constants/value.sql": "CONSTANT (name value, value 1);",
                "models/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
            },
            expected_model_names=("orders",),
            expected_diagnostics=(("S024", "warning"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_disabled_placement_enforcement_when_assembling_then_project_and_warning_are_produced(
    test_case: ScopePlacementCompileTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    project_file: str = _PROJECT_FILE + "\n[scopes]\nenforce_placement = false\n"
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": project_file} | test_case.files,
    )
    inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)

    compiled: CompiledProject = assemble_project(inputs=inputs, skip_column_inference=True)

    assert tuple(model.name for model in compiled.models) == test_case.expected_model_names
    assert (
        tuple(
            (diagnostic.code.value, diagnostic.severity.value)
            for diagnostic in compiled.scope_index.diagnostics
        )
        == test_case.expected_diagnostics
    )


@pytest.mark.parametrize(
    "test_case",
    (
        ScopedDeclarationCompileTestCase(
            description="inherited enum contract",
            files={"models/domain/enums/state.sql": "ENUM (name state, members [OPEN, CLOSED]);"},
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
