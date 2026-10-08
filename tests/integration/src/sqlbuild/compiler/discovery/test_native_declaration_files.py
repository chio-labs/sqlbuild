"""Engine parity for the enum, constant, schema, audit, hook, function, seed and macro files."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

from sqlbuild import _native
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import RENDER_REUSE_DECLARATIONS_PREFIX
from sqlbuild.compiler.compile.models import RenderReuseState
from sqlbuild.compiler.discovery._helpers.filesystem import core
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveryFileFault
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    DeclarationFilesParityTestCase,
    DeclarationMismatchTestCase,
    DeclarationReuseTestCase,
    DeepDeclarationHeaderTestCase,
    GeneratedDeclarationFileTestCase,
    NativeSessionTestCase,
    TolerantDeclarationFilesTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    accept_any_declarations,
    declaration_files_outcome,
    generated_declaration_outcomes,
    native_declaration_tag,
    reject_any_contents,
    stage_outcome,
    tolerant_declaration_outcome,
    write_project,
    write_undecodable_hook,
)

_PREVIEW: str = "native-preview"
_NESTING_SUFFIX: str = "contains invalid SQLBuild header syntax: values nest deeper than 256 levels"
_MODEL: bytes = b'MODEL (description "Orders");\nSELECT 1 AS order_id'
_MACRO: bytes = b"def cents(value):\n    return f'{value} * 100'\n"
_ENUMS: bytes = (
    b"ENUM (name order_status, members [PLACED, SHIPPED]);\n"
    b"ENUM (\n  name priority,\n  members (LOW 1, HIGH 2),\n);\n"
)
_CONSTANTS: bytes = (
    b"CONSTANT (name cap, value 3);\n"
    b"CONSTANT (name regions, value ['eu', 'us'], render_as value_list);\n"
    b"CONSTANT (name rate, value constant(value '1.50', type decimal));\n"
)
_SCHEMA: bytes = (
    b'SCHEMA (\r\n  name order_shape,\r\n  description "Order shape",\r\n'
    b"  columns (\r\n    id (type INTEGER, audits [not_null]),\r\n"
    b'    total (type DECIMAL(10, 2), description "Total"),\r\n  ),\r\n);\r\n'
    b"SCHEMA (name wide_order, extends order_shape, columns (note (type VARCHAR)));\n"
)
_AUDIT: bytes = b'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE NOT (@expression)\n'
_MEASUREMENTS: bytes = (
    b"AUDIT (name row_count, evaluation measurement, value total, sample_unit 'rows');\n"
    b'MEASURE (SELECT count(*) AS total FROM __ref("@model"));\n'
    b'EVIDENCE (SELECT * FROM __ref("@model") LIMIT 5);\n'
    b'audit (name no_negative, severity warn);\n-- body\nSELECT * FROM __ref("@model") WHERE x < 0\n'
)
_HOOK: bytes = b'HOOK (\n  description "Record a refresh"\n);\n\n    SELECT 1 AS refreshed\n'
_FUNCTION: bytes = (
    b'FUNCTION (arguments (amount DECIMAL), returns DECIMAL, description "Doubles");\n'
    b"SELECT amount * 2\n"
)
_EVERY_KIND: tuple[tuple[str, bytes], ...] = (
    ("models/marts/orders.sql", _MODEL),
    ("macros/money.py", _MACRO),
    ("macros/__init__.py", b""),
    ("models/marts/_macros/local.py", _MACRO),
    ("enums/status.sql", _ENUMS),
    ("models/marts/_enums/tier.sql", b"ENUM (name tier, members [GOLD]);\n"),
    ("models/marts/_sqlbuild/constants/limits.sql", _CONSTANTS),
    ("constants/global.sql", b"CONSTANT (name ratio, value 1.5);\n"),
    ("models/marts/_sqlbuild/_audits/generic/is_true.sql", _AUDIT),
    ("models/marts/_sqlbuild/audits/singular/orders_ok.sql", _AUDIT),
    ("models/marts/_sqlbuild/_schemas/order_shape.sql", _SCHEMA),
    ("models/marts/_sqlbuild/hooks/sql/record_marts_refresh.sql", _HOOK),
    ("audits/generic/is_true.sql", _AUDIT),
    ("audits/generic/nested/measured.sql", _MEASUREMENTS),
    ("audits/singular/orders_ok.sql", _AUDIT),
    ("schemas/order_shape.sql", _SCHEMA),
    ("hooks/sql/record_refresh.sql", _HOOK),
    ("hooks/sql/_private.sql", b"not a hook"),
    ("functions/sql/double_amount.sql", _FUNCTION),
    ("functions/sql/finance/net_amount.sql", _FUNCTION),
    ("functions/sql/_macros/helpers.py", _MACRO),
    ("seeds/channels.csv", b"id\n1\n"),
    (
        "seeds/seeds.yml",
        b"seeds:\n  - name: channels\n    description: Sales channels.\n"
        b"    columns:\n      - name: id\n        type: INTEGER\n"
        b"  - name: stores\n    description: Stores.\n"
        b"    columns:\n      - name: id\n        type: INTEGER\n",
    ),
    ("seeds/regional/stores.csv", b"id\n2\n"),
    ("seeds/readme.md", b"seeds"),
    ("seeds/archive.csv/notes.txt", b"a directory named like a seed"),
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedDeclarationFileTestCase(
            description="generated enum files",
            kind="enum",
            relative_path="enums/generated.sql",
            case_count=150,
            expected_minimum_parsed=20,
            expected_minimum_failed=60,
            expected_maximum_deferred=8,
        ),
        GeneratedDeclarationFileTestCase(
            description="generated constant files",
            kind="constant",
            relative_path="models/marts/_constants/generated.sql",
            case_count=150,
            expected_minimum_parsed=60,
            expected_minimum_failed=30,
            expected_maximum_deferred=8,
        ),
        GeneratedDeclarationFileTestCase(
            description="generated reusable schema files",
            kind="model_schema",
            relative_path="schemas/generated.sql",
            case_count=150,
            expected_minimum_parsed=50,
            expected_minimum_failed=30,
            expected_maximum_deferred=8,
        ),
        GeneratedDeclarationFileTestCase(
            description="generated audit files",
            kind="audit",
            relative_path="models/marts/_sqlbuild/audits/generic/generated.sql",
            case_count=150,
            expected_minimum_parsed=30,
            expected_minimum_failed=60,
            expected_maximum_deferred=4,
        ),
        GeneratedDeclarationFileTestCase(
            description="generated SQL hook files",
            kind="sql_hook",
            relative_path="hooks/sql/generated.sql",
            case_count=150,
            expected_minimum_parsed=40,
            expected_minimum_failed=40,
            expected_maximum_deferred=4,
        ),
        GeneratedDeclarationFileTestCase(
            description="generated SQL function files",
            kind="sql_function",
            relative_path="functions/sql/generated.sql",
            case_count=150,
            expected_minimum_parsed=50,
            expected_minimum_failed=30,
            expected_maximum_deferred=4,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_declaration_files_when_discovering_then_engines_agree(
    test_case: GeneratedDeclarationFileTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatches: tuple[int, ...]
    tags: Counter[str]

    mismatches, tags = generated_declaration_outcomes(
        project_root=tmp_path, test_case=test_case, monkeypatch=monkeypatch
    )

    assert mismatches == test_case.expected_mismatches
    assert tags["ok"] >= test_case.expected_minimum_parsed, tags
    assert tags["error"] >= test_case.expected_minimum_failed, tags
    assert tags["defer"] <= test_case.expected_maximum_deferred, tags


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationFilesParityTestCase(
            description="global, inherited, local and grouped declarations of every kind",
            files=_EVERY_KIND,
        ),
        DeclarationFilesParityTestCase(
            description="the first failing enum file in path order is reported",
            files=(
                ("enums/a_status.sql", b"ENUM (name a_status, members [placed]);\n"),
                ("enums/b_status.sql", b"ENUM (name b_status);\n"),
            ),
            expected_failure_type="DeclarationParseError",
            expected_message_fragment="member identifiers must be uppercase: 'placed'",
        ),
        DeclarationFilesParityTestCase(
            description="an earlier constant's value fails before a later constant's name",
            files=(
                (
                    "constants/limits.sql",
                    b"CONSTANT (name launch, value 'soon', type DATE);\n"
                    b"CONSTANT (name Bad, value 1);\n",
                ),
            ),
            expected_failure_type="DeclarationParseError",
            expected_message_fragment="constant 'launch'",
        ),
        DeclarationFilesParityTestCase(
            description="an earlier schema's columns fail before a later schema's keys",
            files=(
                (
                    "schemas/shapes.sql",
                    b"SCHEMA (name first_shape, columns (id (nullable maybe)));\n"
                    b"SCHEMA (name second_shape, extra 1, columns (id (type INT)));\n",
                ),
            ),
            expected_failure_type="DeclarationParseError",
            expected_message_fragment="first_shape",
        ),
        DeclarationFilesParityTestCase(
            description="a non-canonical declaration name fails with the identity help",
            files=(("enums/status.sql", b"ENUM (name OrderStatus, members [PLACED]);\n"),),
            expected_failure_type="ResourceIdentityError",
            expected_message_fragment="use snake_case 'order_status'",
        ),
        DeclarationFilesParityTestCase(
            description="a nested declaration root fails before any file is parsed",
            files=(
                ("models/marts/_enums/macros/money.py", _MACRO),
                ("enums/status.sql", b"broken"),
            ),
            expected_failure_type="DeclarationParseError",
            expected_message_fragment="is nested inside another declaration tree",
        ),
        DeclarationFilesParityTestCase(
            description="an unreadable audit file fails with Python's decode error",
            files=(("audits/generic/is_true.sql", b"AUDIT ();\nSELECT '\xff'\n"),),
            expected_failure_type="UnicodeDecodeError",
            expected_message_fragment="invalid start byte",
        ),
        DeclarationFilesParityTestCase(
            description="an unreadable macro file fails with Python's decode error",
            files=(("macros/money.py", b"# \xc3"),),
            expected_failure_type="UnicodeDecodeError",
            expected_message_fragment="unexpected end of data",
        ),
        DeclarationFilesParityTestCase(
            description="a hook with an unsupported key fails with the key suggestion",
            files=(("hooks/sql/refresh.sql", b'HOOK (descripton "Refresh");\nSELECT 1\n'),),
            expected_failure_type="SqlHookParseError",
            expected_message_fragment="has unsupported keys: descripton",
        ),
        DeclarationFilesParityTestCase(
            description="a measurement audit without MEASURE fails",
            files=(
                (
                    "audits/generic/measured.sql",
                    b"AUDIT (evaluation measurement, value total);\nSELECT 1\n",
                ),
            ),
            expected_failure_type="SqlAuditParseError",
            expected_message_fragment="must define exactly one MEASURE(...) block",
        ),
        DeclarationFilesParityTestCase(
            description="a SQL function without a body fails",
            files=(("functions/sql/empty.sql", b"FUNCTION (returns INT);\n  \n"),),
            expected_failure_type="ModelSqlParseError",
            expected_message_fragment="must contain SQL after FUNCTION(...)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declaration_files_when_discovering_through_the_engine_switch_then_inputs_match(
    test_case: DeclarationFilesParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: tuple[object, ...] = stage_outcome(
        project_dir=tmp_path, engine="python", monkeypatch=monkeypatch
    )

    native: tuple[object, ...] = stage_outcome(
        project_dir=tmp_path, engine=_PREVIEW, monkeypatch=monkeypatch
    )

    assert native == python
    assert native[1] == test_case.expected_failure_type
    assert test_case.expected_message_fragment in str(native[2])


@pytest.mark.parametrize(
    "test_case",
    [
        DeepDeclarationHeaderTestCase(
            description="a constant value nested 1k levels",
            kind="constant",
            relative_path="constants/limits.sql",
            prefix="CONSTANT (name cap, value 3);\nCONSTANT (\n  name regions,\n  value ",
            suffix=",\n);\n",
            depth=1_000,
            expected_failure_type="DeclarationParseError",
            expected_message_suffix=f"limits.sql:4' {_NESTING_SUFFIX}",
        ),
        DeepDeclarationHeaderTestCase(
            description="a hook description nested 20k levels",
            kind="sql_hook",
            relative_path="hooks/sql/refresh.sql",
            prefix="HOOK (\n  description ",
            suffix=",\n);\n\nSELECT 1\n",
            depth=20_000,
            expected_failure_type="SqlHookParseError",
            expected_message_suffix=f"refresh.sql:2' {_NESTING_SUFFIX}",
        ),
        DeepDeclarationHeaderTestCase(
            description="a function return type nested 100k levels",
            kind="sql_function",
            relative_path="functions/sql/doubled.sql",
            prefix='FUNCTION (\n  description "Doubles",\n  returns ',
            suffix=",\n);\nSELECT 2\n",
            depth=100_000,
            expected_failure_type="ModelSqlParseError",
            expected_message_suffix=f"doubled.sql:3' {_NESTING_SUFFIX}",
        ),
        DeepDeclarationHeaderTestCase(
            description="a later audit block's value nested 100k levels",
            kind="audit",
            relative_path="audits/generic/is_true.sql",
            prefix="AUDIT (name first);\nSELECT 1\nAUDIT (\n  name second,\n  value ",
            suffix=",\n);\nSELECT 2\n",
            depth=100_000,
            expected_failure_type="SqlAuditParseError",
            expected_message_suffix=f"is_true.sql:5' {_NESTING_SUFFIX}",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deeply_nested_declaration_header_when_discovering_then_engines_report_its_line(
    test_case: DeepDeclarationHeaderTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested: str = "[" * test_case.depth + "1" + "]" * test_case.depth
    contents: str = test_case.prefix + nested + test_case.suffix
    write_project(project_dir=tmp_path, files=((test_case.relative_path, contents.encode()),))
    python: tuple[object, ...] = declaration_files_outcome(
        project_dir=tmp_path, kind=test_case.kind, engine="python", monkeypatch=monkeypatch
    )

    native: tuple[object, ...] = declaration_files_outcome(
        project_dir=tmp_path, kind=test_case.kind, engine=_PREVIEW, monkeypatch=monkeypatch
    )

    assert native == python
    assert native[0] == test_case.expected_failure_type
    assert str(native[1]).endswith(test_case.expected_message_suffix), native[1]
    assert native[2] == test_case.expected_help
    assert (
        native_declaration_tag(file_path=tmp_path / test_case.relative_path, kind=test_case.kind)
        == "error"
    )


@pytest.mark.skipif(sys.platform != "linux", reason="needs file names that are not UTF-8")
@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationFilesParityTestCase(
            description="a hook named with invalid UTF-8 is read by Python under both engines",
            files=(("hooks/sql/refresh.sql", _HOOK),),
            expected_failure_type="ResourceIdentityError",
            expected_message_fragment="refresh_",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hook_named_with_invalid_utf8_when_discovering_then_engines_agree(
    test_case: DeclarationFilesParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_undecodable_hook(project_dir=tmp_path, contents=test_case.files[0][1])
    python: tuple[object, ...] = stage_outcome(
        project_dir=tmp_path, engine="python", monkeypatch=monkeypatch
    )

    native: tuple[object, ...] = stage_outcome(
        project_dir=tmp_path, engine=_PREVIEW, monkeypatch=monkeypatch
    )

    assert native == python
    assert native[1] == test_case.expected_failure_type
    assert test_case.expected_message_fragment in str(native[2])


@pytest.mark.parametrize(
    "test_case",
    [
        TolerantDeclarationFilesTestCase(
            description="broken files of every kind become the same faults",
            files=(
                *_EVERY_KIND,
                ("enums/broken.sql", b"ENUM (name broken);\n"),
                ("constants/broken.sql", b"CONSTANT (name Broken, value 1);\n"),
                ("schemas/broken.sql", b"SCHEMA (name broken_shape);\n"),
                ("audits/generic/broken.sql", b"SELECT 1\n"),
                ("hooks/sql/broken.sql", b"HOOK ();\n"),
                ("functions/sql/broken.sql", b"SELECT 1\n"),
            ),
            expected_resource_faults=3,
            expected_declaration_faults=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_broken_declaration_files_when_discovering_tolerantly_then_faults_match(
    test_case: TolerantDeclarationFilesTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: tuple[object, tuple[DiscoveryFileFault, ...], tuple[DiscoveryFileFault, ...]] = (
        tolerant_declaration_outcome(project_dir=tmp_path, engine="python", monkeypatch=monkeypatch)
    )

    native: tuple[object, tuple[DiscoveryFileFault, ...], tuple[DiscoveryFileFault, ...]] = (
        tolerant_declaration_outcome(project_dir=tmp_path, engine=_PREVIEW, monkeypatch=monkeypatch)
    )

    assert native == python
    assert len(native[1]) == test_case.expected_resource_faults
    assert len(native[2]) == test_case.expected_declaration_faults


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationMismatchTestCase(
            description="Python accepting a file native rejects is a mismatch",
            relative_path="enums/status.sql",
            contents=b"ENUM (name order_status);\n",
            patched_parser="parse_enum_declaration_file",
            patched=accept_any_declarations,
            expected_error_fragment="native declaration_files raised DeclarationParseError",
        ),
        DeclarationMismatchTestCase(
            description="Python failing differently from native is a mismatch",
            relative_path="audits/generic/is_true.sql",
            contents=b"SELECT 1\n",
            patched_parser="parse_sql_audit_file",
            patched=reject_any_contents,
            expected_error_fragment="but the Python compiler raised ValueError('different')",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_disagrees_with_a_native_failure_when_discovering_then_mismatch_raises(
    test_case: DeclarationMismatchTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=((test_case.relative_path, test_case.contents),))
    monkeypatch.setattr(core, test_case.patched_parser, test_case.patched)
    outcome: tuple[object, ...] = stage_outcome(
        project_dir=tmp_path, engine=_PREVIEW, monkeypatch=monkeypatch
    )

    assert outcome[1] == "NativeStageMismatchError"
    assert test_case.expected_error_fragment in str(outcome[2])


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSessionTestCase(
            description="the preview engine keeps its declaration session",
            engine=_PREVIEW,
            expected_session=True,
        ),
        NativeSessionTestCase(
            description="the shipped engine reads declaration files in Python",
            engine="native",
            expected_session=False,
        ),
        NativeSessionTestCase(
            description="the Python engine reads declaration files in Python",
            engine="python",
            expected_session=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_discovering_then_native_session_is_kept_only_for_preview(
    test_case: NativeSessionTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=_EVERY_KIND)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine)

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    assert (
        isinstance(discovered.native_session, _native.NativeDiscoverySession)
        is test_case.expected_session
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationReuseTestCase(
            description="a model edit reuses every stored declaration file",
            files=_EVERY_KIND,
            edited_path="models/marts/orders.sql",
            edited_contents=_MODEL + b" -- edited\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_preview_compile_when_only_a_model_changes_then_declaration_files_are_reused(
    test_case: DeclarationReuseTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, _PREVIEW)
    first_session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=None, changed_paths=None
    )
    first: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=tmp_path, declaration_reuse=first_session
    )
    first_session.plan_models(model_files=first.model_files)
    state: RenderReuseState | None = first_session.stored_state()
    assert state is not None
    _ = (tmp_path / test_case.edited_path).write_bytes(test_case.edited_contents)
    second_session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=state, changed_paths=frozenset({test_case.edited_path})
    )

    second: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=tmp_path, declaration_reuse=second_session
    )
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
    fresh: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    assert any(name.startswith(RENDER_REUSE_DECLARATIONS_PREFIX) for name in state.group_payloads)
    assert second.native_session is test_case.expected_reused_session
    assert render_stage_capture(second) == render_stage_capture(fresh)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
