"""Sources attached by the native model loop and assembled into the native compiled project."""

from dataclasses import asdict
from pathlib import Path

import pytest

import sqlbuild._native as _native
from sqlbuild._native import CompileInputError
from sqlbuild.compiler.compile.types import CompiledProjectView, CompiledSourceView, SourceInput
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    NativeSourceAttachmentTestCase,
    NativeSourceErrorTestCase,
    NativeSourceKeysTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    column_metadata,
    compile_source_project,
)

_TEMPLATED_SOURCE_YML: str = (
    "sources:\n"
    "  - name: raw_orders\n"
    "    database: lake_${region}\n"
    "    schema: raw_${region}\n"
    "    table: orders_${region}\n"
    "    description: Orders from ${region}.\n"
    "    meta:\n      owner: team_${region}\n"
    "    columns:\n"
    "      - name: amount\n"
    "        type: DECIMAL\n"
    "        description: Amount in ${region}.\n"
    "        audits:\n"
    "          - accepted_values:\n"
    "              values: ['${region}']\n"
)
_EXPRESSION_SOURCE_YML: str = (
    "sources:\n"
    "  - name: open_orders\n"
    "    contract: none\n"
    '    expression: "SELECT @cents(1) AS cents, @enum(\\"order_status\\").PLACED AS status,'
    ' @const(\\"order_cap\\") AS cap, \'@@region\' AS region"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSourceAttachmentTestCase(
            description="templated metadata, columns and audit arguments under the default contract",
            source_yml=_TEMPLATED_SOURCE_YML,
            source_name="raw_orders",
            expected_entry={
                "database": "lake_eu",
                "schema": "raw_eu",
                "table": "orders_eu",
                "description": "Orders from eu.",
                "contract": "enforced",
                "meta": {"owner": "team_eu"},
                "column_metadata": (("Amount in eu.", ({"values": ["eu"]},)),),
            },
            expected_usages=(),
        ),
        NativeSourceAttachmentTestCase(
            description="expression expanding macros, declarations and variables",
            source_yml=_EXPRESSION_SOURCE_YML,
            source_name="open_orders",
            expected_entry={
                "expression": "SELECT 1 * 100 AS cents, 'PLACED' AS status, 3 AS cap,"
                " 'eu' AS region",
                "contract": "none",
            },
            expected_usages=("enum:order_status", "constant:order_cap", "macro:cents"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_compiling_then_native_project_holds_its_attached_entry(
    test_case: NativeSourceAttachmentTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project: CompiledProjectView
    project, inputs = compile_source_project(
        project_dir=tmp_path, source_yml=test_case.source_yml, monkeypatch=monkeypatch
    )

    source: CompiledSourceView = project.sources[0]
    source_input: SourceInput = inputs.source_inputs[0]
    entry: dict[str, object] = asdict(source.source_entry)
    entry["column_metadata"] = tuple(map(column_metadata, source.source_entry.columns))
    assert isinstance(source, _native.NativeCompiledSource)
    assert isinstance(source_input, _native.NativeSourceInput)
    assert source.name == test_case.source_name
    assert {key: entry[key] for key in test_case.expected_entry} == test_case.expected_entry
    assert (
        tuple(
            f"{usage.declaration.kind.value}:{usage.declaration.name}"
            for usage in source_input.declaration_usages
        )
        == test_case.expected_usages
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSourceKeysTestCase(
            description="column and table unique audits with templated column metadata",
            source_yml=(
                "sources:\n"
                "  - name: raw_orders\n"
                "    audits:\n      - unique:\n          column: order_id\n"
                "    columns:\n"
                "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
                "        description: Order in ${region}.\n"
                "      - name: customer_id\n        type: INTEGER\n"
                "        audits:\n          - unique\n          - not_null\n"
                "  - name: raw_events\n"
                "    columns:\n      - name: event_id\n        type: INTEGER\n"
            ),
            expected_keys={"source:raw_orders": (("customer_id",), ("order_id",))},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_keyed_sources_when_deriving_relation_keys_then_native_views_match_entries(
    test_case: NativeSourceKeysTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project: CompiledProjectView
    project, _ = compile_source_project(
        project_dir=tmp_path, source_yml=test_case.source_yml, monkeypatch=monkeypatch
    )

    from_entries: dict[str, tuple[tuple[str, ...], ...]] = _native.declared_relation_keys(
        model_rows=(), seeds=(), sources=tuple(source.source_entry for source in project.sources)
    )
    compiled: dict[str, tuple[tuple[str, ...], ...]] = _native.compiled_relation_keys(project)
    assert from_entries == test_case.expected_keys
    assert {identity: compiled[identity] for identity in from_entries} == from_entries


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSourceErrorTestCase(
            description="unknown variable in column metadata",
            source_yml=(
                "sources:\n  - name: raw_orders\n    columns:\n      - name: amount\n"
                "        meta:\n          unit: ${currency}\n"
            ),
            expected_message=(
                "source raw_orders column amount meta references unknown variable 'currency'"
            ),
            expects_help=False,
        ),
        NativeSourceErrorTestCase(
            description="cursor intrinsic in an expression",
            source_yml=(
                "sources:\n  - name: raw_orders\n"
                '    expression: "SELECT 1 AS id WHERE id > __cursor_start()"\n'
            ),
            expected_message=(
                "Source expression 'raw_orders' uses cursor intrinsics, which are only"
                " supported in cursor-based incremental model query SQL"
            ),
            expects_help=False,
        ),
        NativeSourceErrorTestCase(
            description="expression that does not parse as a relation",
            source_yml='sources:\n  - name: raw_orders\n    expression: "SELECT FROM WHERE"\n',
            expected_message="SQL syntax error in source expression 'raw_orders'",
            expects_help=True,
        ),
        NativeSourceErrorTestCase(
            description="first of several expressions that do not parse",
            source_yml=(
                "sources:\n"
                '  - name: open_orders\n    expression: "SELECT 1 AS id"\n'
                '  - name: first_orders\n    expression: "SELECT FROM WHERE"\n'
                '  - name: second_orders\n    expression: "SELECT , FROM"\n'
            ),
            expected_message="SQL syntax error in source expression 'first_orders'",
            expects_help=True,
        ),
        NativeSourceErrorTestCase(
            description="earlier source error before a later expression that does not parse",
            source_yml=(
                "sources:\n  - name: raw_orders\n    columns:\n      - name: amount\n"
                "        meta:\n          unit: ${currency}\n"
                '  - name: broken_orders\n    expression: "SELECT FROM WHERE"\n'
            ),
            expected_message=(
                "source raw_orders column amount meta references unknown variable 'currency'"
            ),
            expects_help=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_source_when_compiling_then_native_attachment_rejects_it(
    test_case: NativeSourceErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CompileInputError) as raised:
        _ = compile_source_project(
            project_dir=tmp_path, source_yml=test_case.source_yml, monkeypatch=monkeypatch
        )

    assert test_case.expected_message in str(raised.value)
    assert (raised.value.help is not None) is test_case.expects_help
