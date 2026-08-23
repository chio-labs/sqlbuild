"""Compile-time resolution for enum and constant declarations."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.constants import MACRO_TOKEN, SQL_QUOTE_TOKENS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
    EnumMember,
)
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn, SchemaModelEntry

_ENUM_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"@enum\s*\(\s*(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)\s*\)\s*\.\s*(?P<member>[A-Za-z_][A-Za-z0-9_]*)"
)
_CONSTANT_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"@const\s*\(\s*(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)\s*\)"
)
_DECLARATION_REFERENCE_START_PATTERN: re.Pattern[str] = re.compile(r"@(?P<kind>enum|const)\b")
_CONTEXT: str = "Enum and constant expansion"
_ACCEPTED_VALUES_AUDIT: str = "accepted_values"
_ENUM_REFERENCE_KIND: str = "enum"


def build_public_declaration_indexes(
    *, discovered_inputs: DiscoveredProjectInputs
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]:
    """Build collision-checked project-global declaration indexes."""

    enums: dict[str, EnumDeclaration] = {}
    constants: dict[str, ConstantDeclaration] = {}
    enum_file: DiscoveredEnumFile
    for enum_file in discovered_inputs.enum_files:
        declaration: EnumDeclaration
        for declaration in enum_file.declarations:
            enums = _with_declaration(
                declarations=enums,
                declaration=declaration,
                kind="enum",
            )
    constant_file: DiscoveredConstantFile
    for constant_file in discovered_inputs.constant_files:
        constant_declaration: ConstantDeclaration
        for constant_declaration in constant_file.declarations:
            constants = _with_declaration(
                declarations=constants,
                declaration=constant_declaration,
                kind="constant",
            )
    return enums, constants


def build_model_declaration_indexes(
    *, model_file: DiscoveredSqlModelFile
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]:
    """Build collision-checked declaration indexes private to one model."""

    return (
        {declaration.name: declaration for declaration in model_file.enum_declarations},
        {declaration.name: declaration for declaration in model_file.constant_declarations},
    )


def expand_declaration_references(
    *,
    sql: str,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    constants: dict[str, ConstantDeclaration],
) -> str:
    """Resolve enum-member and constant references to SQL scalar literals."""

    rendered_sql: str
    rendered_sql, _spans = expand_declaration_references_with_spans(
        sql=sql, file_path=file_path, enums=enums, constants=constants
    )
    return rendered_sql


def expand_declaration_references_with_spans(
    *,
    sql: str,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    constants: dict[str, ConstantDeclaration],
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Resolve declaration references, returning the span of every substitution."""

    rendered_parts: list[str] = []
    spans: list[ExpansionSpan] = []
    output_length: int = 0
    cursor: int = 0
    while cursor < len(sql):
        reference_start: int | None = _find_next_reference_start(sql=sql, start=cursor)
        if reference_start is None:
            rendered_parts.append(sql[cursor:])
            break
        leading_literal: str = sql[cursor:reference_start]
        rendered_parts.append(leading_literal)
        output_length += len(leading_literal)
        start_match: re.Match[str] | None = _DECLARATION_REFERENCE_START_PATTERN.match(
            sql, reference_start
        )
        if start_match is None:
            raise CompileInputError(f"Invalid declaration reference in '{file_path}'")
        kind: str = start_match.group("kind")
        if kind == _ENUM_REFERENCE_KIND:
            replacement: str
            next_cursor: int
            replacement, next_cursor = _resolve_enum_reference(
                sql=sql,
                reference_start=reference_start,
                file_path=file_path,
                enums=enums,
            )
        else:
            replacement, next_cursor = _resolve_constant_reference(
                sql=sql,
                reference_start=reference_start,
                file_path=file_path,
                constants=constants,
            )
        rendered_parts.append(replacement)
        spans.append(
            ExpansionSpan(
                source_start=reference_start,
                source_end=next_cursor,
                output_start=output_length,
                output_end=output_length + len(replacement),
            )
        )
        output_length += len(replacement)
        cursor = next_cursor
    return "".join(rendered_parts), tuple(spans)


def resolve_enum_contract_columns(
    *,
    schema_entry: SchemaModelEntry | None,
    config_values: dict[str, object],
    enums: dict[str, EnumDeclaration],
) -> tuple[SchemaModelEntry | None, dict[str, EnumDeclaration]]:
    """Resolve enum column types and synthesize enforced accepted-values audits."""

    if schema_entry is None:
        return None, {}
    contract_enforced: bool = config_values.get("contract") == ContractPolicy.ENFORCED
    enum_columns: dict[str, EnumDeclaration] = {}
    columns: list[SchemaColumn] = []
    column: SchemaColumn
    for column in schema_entry.columns:
        declaration: EnumDeclaration | None = enums.get(column.type or "")
        if declaration is None:
            columns.append(column)
            continue
        enum_columns[column.name] = declaration
        audits: tuple[SchemaAuditInstance, ...] = column.audits
        if contract_enforced:
            generated_audit: SchemaAuditInstance = SchemaAuditInstance(
                definition_name=_ACCEPTED_VALUES_AUDIT,
                arguments={"values": tuple(member.value for member in declaration.members)},
            )
            if generated_audit not in audits:
                audits = (*audits, generated_audit)
        columns.append(replace(column, type=declaration.scalar_type, audits=audits))
    return replace(schema_entry, columns=tuple(columns)), enum_columns


def _with_declaration[T: EnumDeclaration | ConstantDeclaration](
    *, declarations: dict[str, T], declaration: T, kind: str
) -> dict[str, T]:
    existing: T | None = declarations.get(declaration.name)
    if existing is not None:
        raise CompileInputError(
            f"Duplicate public {kind} '{declaration.name}' in {existing.relative_path} and "
            f"{declaration.relative_path}"
        )
    return declarations | {declaration.name: declaration}


def _resolve_enum_reference(
    *,
    sql: str,
    reference_start: int,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
) -> tuple[str, int]:
    match: re.Match[str] | None = _ENUM_REFERENCE_PATTERN.match(sql, reference_start)
    if match is None:
        raise CompileInputError(
            f"Invalid enum reference in '{file_path}'; use @enum(\"name\").MEMBER"
        )
    name: str = match.group("name")
    declaration: EnumDeclaration | None = enums.get(name)
    if declaration is None:
        scope_help: str = " in this model" if name.startswith("_") else ""
        raise CompileInputError(f"Unknown enum '{name}'{scope_help} in '{file_path}'")
    member_name: str = match.group("member")
    member: EnumMember | None = next(
        (candidate for candidate in declaration.members if candidate.name == member_name),
        None,
    )
    if member is None:
        available: str = ", ".join(item.name for item in declaration.members)
        raise CompileInputError(
            f"Unknown member '{member_name}' for enum '{name}' in '{file_path}'. "
            f"Available members: {available}"
        )
    return _render_scalar(value=member.value), match.end()


def _resolve_constant_reference(
    *,
    sql: str,
    reference_start: int,
    file_path: Path,
    constants: dict[str, ConstantDeclaration],
) -> tuple[str, int]:
    match: re.Match[str] | None = _CONSTANT_REFERENCE_PATTERN.match(sql, reference_start)
    if match is None:
        raise CompileInputError(
            f"Invalid constant reference in '{file_path}'; use @const(\"name\")"
        )
    name: str = match.group("name")
    declaration: ConstantDeclaration | None = constants.get(name)
    if declaration is None:
        scope_help: str = " in this model" if name.startswith("_") else ""
        raise CompileInputError(f"Unknown constant '{name}'{scope_help} in '{file_path}'")
    return _render_scalar(value=declaration.value), match.end()


def _render_scalar(*, value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"


def _find_next_reference_start(*, sql: str, start: int) -> int | None:
    if MACRO_TOKEN not in sql[start:]:
        return None
    index: int = start
    while index < len(sql):
        character: str = sql[index]
        if character in SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if character == MACRO_TOKEN and _DECLARATION_REFERENCE_START_PATTERN.match(sql, index):
            return index
        index += 1
    return None
