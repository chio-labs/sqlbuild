"""Declaration files discovered by the native engine, materialised as Python discovery records."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.models import MeasurementContract
from sqlbuild.compiler.auditing.types import AuditEvaluationMode
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    materialise_native_files,
    native_collection,
    native_failure,
    native_locations,
    native_project_tree,
    native_read_error,
    native_request,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery._helpers.sql.declarations import typed_constant_declaration
from sqlbuild.compiler.discovery._helpers.sql.model_files import project_native_header_values
from sqlbuild.compiler.discovery._helpers.sql.schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    NATIVE_DEFERRED_TAG,
    NATIVE_FAILED_TAG,
    NATIVE_PARSED_TAG,
    SQL_AUDIT_HEADER_KEYS,
    SQL_FUNCTION_HEADER_KEYS,
    SQL_HOOK_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
    DiscoveredModelSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveryFileFault,
    EnumDeclaration,
    EnumMember,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.discovery.types import NativeFileScope, NativeLocation, NativeScopeFields
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

type _NativeDeclarationFile = tuple[str, NativeFileScope | None, tuple[object, ...]]
type _PythonParse[RecordT] = Callable[..., RecordT]
type _Build[RecordT] = Callable[..., RecordT]
type _EnumPayload = tuple[str, dict[str, object], str]
type _ConstantPayload = tuple[str, dict[str, object], str | None, str | None]
type _SchemaPayload = tuple[str, str | None, str | None, dict[str, object], list[NativeLocation]]

_SESSION_MEMO_KEY: str = "native_discovery_session"


def native_enum_files(
    *,
    project_dir: Path,
    isolate_declaration_kind: bool,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredEnumFile],
) -> tuple[DiscoveredEnumFile, ...]:
    """Discover the enum files natively; Python parses the files native parsing defers."""

    return _native_records(
        project_dir=project_dir,
        kind=DeclarationKind.ENUM,
        isolate_kind=isolate_declaration_kind,
        build=_enum_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_constant_files(
    *,
    project_dir: Path,
    isolate_declaration_kind: bool,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredConstantFile],
) -> tuple[DiscoveredConstantFile, ...]:
    """Discover the constant files natively; Python normalises each constant's value."""

    return _native_records(
        project_dir=project_dir,
        kind=DeclarationKind.CONSTANT,
        isolate_kind=isolate_declaration_kind,
        build=_constant_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_model_schema_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredModelSchemaFile],
) -> tuple[DiscoveredModelSchemaFile, ...]:
    """Discover the reusable model schema files natively; Python parses each schema's columns."""

    return _native_records(
        project_dir=project_dir,
        kind="model_schema",
        build=_schema_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_sql_function_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredSqlFunctionFile],
) -> tuple[DiscoveredSqlFunctionFile, ...]:
    """Discover the SQL function files natively."""

    return _native_records(
        project_dir=project_dir,
        kind="sql_function",
        build=_function_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_sql_hook_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredSqlHookFile],
) -> tuple[DiscoveredSqlHookFile, ...]:
    """Discover the named SQL hook files natively."""

    return _native_records(
        project_dir=project_dir,
        kind="sql_hook",
        build=_hook_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_audit_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    parse_with_python: _PythonParse[DiscoveredAuditFile],
) -> tuple[DiscoveredAuditFile, ...]:
    """Discover the generic and singular audit files natively."""

    return _native_records(
        project_dir=project_dir,
        kind="audit",
        build=_audit_file,
        parse_with_python=parse_with_python,
        on_fault=on_fault,
    )


def native_macro_files(
    *,
    project_dir: Path,
    isolate_declaration_kind: bool,
    read_with_python: _PythonParse[DiscoveredMacroFile],
) -> tuple[DiscoveredMacroFile, ...]:
    """Discover and read the macro files natively; Python reads the files native reading defers."""

    return _native_records(
        project_dir=project_dir,
        kind=DeclarationKind.MACRO,
        isolate_kind=isolate_declaration_kind,
        build=_macro_file,
        parse_with_python=read_with_python,
        on_fault=None,
    )


def native_seed_files(*, project_dir: Path) -> tuple[DiscoveredSeedFile, ...]:
    """Discover the seed files natively."""

    return tuple(
        DiscoveredSeedFile(file_path=project_dir / relative_path, relative_path=Path(relative_path))
        for relative_path, _scope, _payload in _native_files(project_dir=project_dir, kind="seed")
    )


def retained_discovery_session(*, project_dir: Path) -> _native.NativeDiscoverySession | None:
    """Return the native session this discovery pass read its declaration files with, if any."""

    session: object = DirectorySnapshot.current(project_dir=project_dir).memo.get(_SESSION_MEMO_KEY)
    return session if isinstance(session, _native.NativeDiscoverySession) else None


def _native_records[RecordT](
    *,
    project_dir: Path,
    kind: str,
    build: _Build[RecordT],
    parse_with_python: _PythonParse[RecordT],
    on_fault: Callable[[DiscoveryFileFault], None] | None,
    isolate_kind: bool = False,
) -> tuple[RecordT, ...]:
    files: list[_NativeDeclarationFile] = _native_files(
        project_dir=project_dir, kind=kind, isolate_kind=isolate_kind
    )
    return materialise_native_files(
        project_dir=project_dir,
        files=((Path(relative_path), (scope, payload)) for relative_path, scope, payload in files),
        build=lambda relative_path, item: _record(
            project_dir=project_dir,
            relative_path=relative_path,
            item=item,
            build=build,
            parse_with_python=parse_with_python,
        ),
        on_fault=on_fault,
    )


def _native_files(
    *, project_dir: Path, kind: str, isolate_kind: bool = False
) -> list[_NativeDeclarationFile]:
    with DirectorySnapshot.scope(project_dir=project_dir):
        tree: _native.NativeProjectTree = native_project_tree(project_dir)
        files: list[_NativeDeclarationFile] = native_collection(
            result=_discovery_session(project_dir=project_dir).collection(kind, tree, isolate_kind),
            project_dir=project_dir,
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
    return files


def _discovery_session(*, project_dir: Path) -> _native.NativeDiscoverySession:
    snapshot: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    session: _native.NativeDiscoverySession | None = retained_discovery_session(
        project_dir=project_dir
    )
    if session is not None:
        return session
    created: _native.NativeDiscoverySession = _native.NativeDiscoverySession(
        native_request(
            project_dir=project_dir,
            fields={
                "function_keys": sorted(SQL_FUNCTION_HEADER_KEYS),
                "audit_keys": sorted(SQL_AUDIT_HEADER_KEYS),
                "hook_keys": sorted(SQL_HOOK_HEADER_KEYS),
            },
        )
    )
    snapshot.memo[_SESSION_MEMO_KEY] = created
    return created


def _record[RecordT](
    *,
    project_dir: Path,
    relative_path: Path,
    item: tuple[NativeFileScope | None, tuple[object, ...]],
    build: _Build[RecordT],
    parse_with_python: _PythonParse[RecordT],
) -> RecordT:
    """Build a parsed file or raise Python's error for it; Python parses the files native defers."""

    scope, payload = item
    tag: object = payload[0]
    if tag == NATIVE_DEFERRED_TAG:
        report_native_fallback(site=NativeFallbackSite.DECLARATION_FILE)
        return parse_with_python(relative_path=relative_path, scope=scope)
    if tag == NATIVE_PARSED_TAG:
        return build(
            project_dir=project_dir, relative_path=relative_path, scope=scope, payload=payload
        )
    if tag == NATIVE_FAILED_TAG:
        raise native_failure(payload)
    raise native_read_error(payload=payload, file_path=project_dir / relative_path)


def _raise_partial_failure(failure: object) -> None:
    if failure is not None:
        raise native_failure(cast(tuple[object, ...], failure))


def _scope_fields(scope: NativeFileScope | None) -> NativeScopeFields:
    if scope is None:
        return NativeScopeFields()
    _kind, scope_kind, ownership_root, owning_path, declaration_root = scope
    return NativeScopeFields(
        scope_kind=ScopeKind(scope_kind),
        ownership_root=_optional_path(ownership_root),
        owning_path=_optional_path(owning_path),
        declaration_root=_optional_path(declaration_root),
    )


def _optional_path(text: str | None) -> Path | None:
    return None if text is None else Path(text)


def _audit_block(block: tuple[object, ...]) -> DiscoveredAuditBlock:
    audit_index, values, sql_body, name, mode, measure_sql, evidence_sql = block
    header_values: dict[str, object] = project_native_header_values(cast(dict[str, object], values))
    evaluation_mode: AuditEvaluationMode = AuditEvaluationMode(str(mode))
    return DiscoveredAuditBlock(
        audit_index=cast(int, audit_index),
        header_values=header_values,
        sql_body=str(sql_body),
        name=cast(str | None, name),
        evaluation_mode=evaluation_mode,
        measurement_contract=(
            MeasurementContract(
                value_column=cast(str, header_values["value"]),
                sample_count_column=cast(str | None, header_values.get("sample_count")),
                sample_unit=cast(str | None, header_values.get("sample_unit")),
            )
            if evaluation_mode is AuditEvaluationMode.MEASUREMENT
            else None
        ),
        measure_sql=cast(str | None, measure_sql),
        evidence_sql=cast(str | None, evidence_sql),
    )


def _enum_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredEnumFile:
    _tag, contents, declarations = payload
    return DiscoveredEnumFile(
        file_path=project_dir / relative_path,
        relative_path=relative_path,
        contents=str(contents),
        declarations=tuple(
            _enum_declaration(relative_path=relative_path, declaration=declaration)
            for declaration in cast(list[_EnumPayload], declarations)
        ),
        **_scope_fields(scope),
    )


def _enum_declaration(*, relative_path: Path, declaration: _EnumPayload) -> EnumDeclaration:
    name, members, scalar_type = declaration
    projected: dict[str, object] = project_native_header_values(members)
    return EnumDeclaration(
        name=name,
        members=tuple(
            EnumMember(name=member, value=cast(str | int, value))
            for member, value in projected.items()
        ),
        scalar_type=scalar_type,
        relative_path=relative_path,
    )


def _constant_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredConstantFile:
    _tag, contents, declarations, failure = payload
    file_path: Path = project_dir / relative_path
    constants: tuple[ConstantDeclaration, ...] = tuple(
        _constant_declaration(
            file_path=file_path, relative_path=relative_path, declaration=declaration
        )
        for declaration in cast(list[_ConstantPayload], declarations)
    )
    _raise_partial_failure(failure)
    return DiscoveredConstantFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=str(contents),
        declarations=constants,
        **_scope_fields(scope),
    )


def _constant_declaration(
    *, file_path: Path, relative_path: Path, declaration: _ConstantPayload
) -> ConstantDeclaration:
    name, value, explicit_type, render_as = declaration
    return typed_constant_declaration(
        name=name,
        value=project_native_header_values(value)["value"],
        explicit_type=explicit_type,
        render_as_text=render_as,
        file_path=file_path,
        relative_path=relative_path,
        model_name=None,
    )


def _schema_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredModelSchemaFile:
    _tag, contents, declarations, failure = payload
    file_path: Path = project_dir / relative_path
    schemas: tuple[ModelSchemaDeclaration, ...] = tuple(
        _schema_declaration(
            file_path=file_path, relative_path=relative_path, declaration=declaration
        )
        for declaration in cast(list[_SchemaPayload], declarations)
    )
    _raise_partial_failure(failure)
    return DiscoveredModelSchemaFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=str(contents),
        declarations=schemas,
        **_scope_fields(scope),
    )


def _schema_declaration(
    *, file_path: Path, relative_path: Path, declaration: _SchemaPayload
) -> ModelSchemaDeclaration:
    name, description, extends, columns, locations = declaration
    return ModelSchemaDeclaration(
        name=name,
        description=description,
        extends=extends,
        columns=parse_schema_columns(
            raw_columns=project_native_header_values(columns).get("columns"),
            file_path=file_path,
            label=f"schema '{name}'",
            error_class=DeclarationParseError,
            column_locations=native_locations(locations=locations, relative_path=relative_path),
            require_columns=True,
        ),
        relative_path=relative_path,
    )


def _function_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredSqlFunctionFile:
    _ = scope
    _tag, contents, header_values, body_sql = payload
    return DiscoveredSqlFunctionFile(
        file_path=project_dir / relative_path,
        relative_path=relative_path,
        contents=str(contents),
        header_values=project_native_header_values(cast(dict[str, object], header_values)),
        body_sql=str(body_sql),
    )


def _hook_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredSqlHookFile:
    _tag, contents, header_values, sql_body, name, description = payload
    return DiscoveredSqlHookFile(
        file_path=project_dir / relative_path,
        relative_path=relative_path,
        contents=str(contents),
        header_values=project_native_header_values(cast(dict[str, object], header_values)),
        sql_body=str(sql_body),
        name=str(name),
        description=cast(str | None, description),
        **_scope_fields(scope),
    )


def _audit_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredAuditFile:
    _tag, contents, blocks = payload
    return DiscoveredAuditFile(
        file_path=project_dir / relative_path,
        relative_path=relative_path,
        contents=str(contents),
        blocks=tuple(_audit_block(block) for block in cast(list[tuple[object, ...]], blocks)),
        declaration_kind=DeclarationKind(cast(NativeFileScope, scope)[0]),
        **_scope_fields(scope),
    )


def _macro_file(
    *,
    project_dir: Path,
    relative_path: Path,
    scope: NativeFileScope | None,
    payload: tuple[object, ...],
) -> DiscoveredMacroFile:
    _tag, contents = payload
    return DiscoveredMacroFile(
        file_path=project_dir / relative_path,
        relative_path=relative_path,
        contents=str(contents),
        **_scope_fields(scope),
    )
