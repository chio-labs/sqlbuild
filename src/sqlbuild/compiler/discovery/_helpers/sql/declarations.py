"""Parsing helpers for authored public SQL declaration files."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    header_column_locations,
    parse_header_values,
)
from sqlbuild.compiler.discovery._helpers.sql.schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError, ModelSqlParseError
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    EnumDeclaration,
    EnumMember,
    ModelSchemaDeclaration,
)
from sqlbuild.sql_values.constants import MISSING_SQL_VALUE
from sqlbuild.sql_values.exceptions import SqlValueValidationError
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.models import AuthoredSqlValueCall, SqlValue
from sqlbuild.sql_values.types import CollectionRendering, SqlValueKind

_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DECLARATION_START_PATTERN: re.Pattern[str] = re.compile(r"(?P<kind>ENUM|CONSTANT|SCHEMA)\s*\(")
_VARCHAR_TYPE: str = "VARCHAR"
_INTEGER_TYPE: str = "INTEGER"
_STATEMENT_TERMINATOR: str = ";"
_ESCAPE_CHARACTER: str = "\\"
_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"'})
_OPEN_PARENTHESIS: str = "("
_CLOSE_PARENTHESIS: str = ")"


@dataclass(frozen=True)
class _ParsedDeclarationHeader:
    values: dict[str, object]
    header: str
    header_start: int


def parse_enum_declaration_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> tuple[EnumDeclaration, ...]:
    """Parse all public enum declarations in one file."""

    return tuple(
        _parse_enum_declaration(
            values=parsed_header.values,
            file_path=file_path,
            relative_path=relative_path,
            model_name=None,
        )
        for parsed_header in _parse_declaration_headers(
            contents=contents,
            file_path=file_path,
            expected_kind="ENUM",
        )
    )


def parse_constant_declaration_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> tuple[ConstantDeclaration, ...]:
    """Parse all public constant declarations in one file."""

    return tuple(
        _parse_constant_declaration(
            name=parsed_header.values.get("name"),
            value=parsed_header.values.get("value", MISSING_SQL_VALUE),
            explicit_type=parsed_header.values.get("type", MISSING_SQL_VALUE),
            raw_render_as=parsed_header.values.get("render_as", MISSING_SQL_VALUE),
            file_path=file_path,
            relative_path=relative_path,
            model_name=None,
            unknown_keys=set(parsed_header.values) - {"name", "value", "type", "render_as"},
        )
        for parsed_header in _parse_declaration_headers(
            contents=contents,
            file_path=file_path,
            expected_kind="CONSTANT",
        )
    )


def parse_model_schema_declaration_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> tuple[ModelSchemaDeclaration, ...]:
    """Parse all public reusable model schemas in one file."""

    declarations: list[ModelSchemaDeclaration] = []
    parsed_header: _ParsedDeclarationHeader
    for parsed_header in _parse_declaration_headers(
        contents=contents,
        file_path=file_path,
        expected_kind="SCHEMA",
    ):
        values: dict[str, object] = parsed_header.values
        unknown_keys: set[str] = set(values) - {"name", "description", "extends", "columns"}
        if unknown_keys:
            raise DeclarationParseError(
                f"{file_path} schema has unknown keys: {', '.join(sorted(unknown_keys))}"
            )
        name: str = _parse_declaration_name(
            raw_name=values.get("name"),
            file_path=file_path,
            kind="schema",
            model_name=None,
        )
        description: str | None = _parse_optional_declaration_string(
            raw_value=values.get("description"),
            file_path=file_path,
            label=f"schema '{name}' description",
        )
        extends: str | None = _parse_optional_declaration_identifier(
            raw_value=values.get("extends"),
            file_path=file_path,
            label=f"schema '{name}' extends",
        )
        declarations.append(
            ModelSchemaDeclaration(
                name=name,
                description=description,
                extends=extends,
                columns=parse_schema_columns(
                    raw_columns=values.get("columns"),
                    file_path=file_path,
                    label=f"schema '{name}'",
                    error_class=DeclarationParseError,
                    column_locations=header_column_locations(
                        contents=contents,
                        header=parsed_header.header,
                        header_start=parsed_header.header_start,
                        relative_path=relative_path,
                    ),
                    require_columns=True,
                ),
                relative_path=relative_path,
            )
        )
    return tuple(declarations)


def _parse_optional_declaration_string(
    *, raw_value: object | None, file_path: Path, label: str
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise DeclarationParseError(f"{file_path} {label} must be a non-empty string")
    return raw_value


def _parse_optional_declaration_identifier(
    *, raw_value: object | None, file_path: Path, label: str
) -> str | None:
    value: str | None = _parse_optional_declaration_string(
        raw_value=raw_value,
        file_path=file_path,
        label=label,
    )
    if value is not None and not _IDENTIFIER_PATTERN.fullmatch(value):
        raise DeclarationParseError(f"{file_path} {label} must be an identifier")
    return value


def parse_model_enum_declarations(
    *, raw_value: object | None, model_name: str, relative_path: Path
) -> tuple[EnumDeclaration, ...]:
    """Normalize model-header enum declarations into scoped facts."""

    if raw_value is None:
        return ()
    if not isinstance(raw_value, dict):
        raise DeclarationParseError(f"{relative_path} model 'enums' must be a mapping")
    declarations: list[EnumDeclaration] = []
    raw_name: object
    raw_members: object
    for raw_name, raw_members in cast(dict[object, object], raw_value).items():
        declarations.append(
            _parse_enum_declaration(
                values={"name": raw_name, "members": raw_members},
                file_path=relative_path,
                relative_path=relative_path,
                model_name=model_name,
            )
        )
    return tuple(declarations)


def parse_model_constant_declarations(
    *, raw_value: object | None, model_name: str, relative_path: Path
) -> tuple[ConstantDeclaration, ...]:
    """Normalize model-header constant declarations into scoped facts."""

    if raw_value is None:
        return ()
    if not isinstance(raw_value, dict):
        raise DeclarationParseError(f"{relative_path} model 'constants' must be a mapping")
    declarations: list[ConstantDeclaration] = []
    raw_name: object
    raw_value_item: object
    for raw_name, raw_value_item in cast(dict[object, object], raw_value).items():
        declarations.append(
            _parse_constant_declaration(
                name=raw_name,
                value=raw_value_item,
                explicit_type=MISSING_SQL_VALUE,
                raw_render_as=MISSING_SQL_VALUE,
                file_path=relative_path,
                relative_path=relative_path,
                model_name=model_name,
                unknown_keys=set(),
            )
        )
    return tuple(declarations)


def _parse_declaration_headers(
    *, contents: str, file_path: Path, expected_kind: str
) -> tuple[_ParsedDeclarationHeader, ...]:
    headers: list[_ParsedDeclarationHeader] = []
    cursor: int = 0
    while cursor < len(contents):
        cursor = _skip_whitespace(contents=contents, start=cursor)
        if cursor == len(contents):
            break
        match: re.Match[str] | None = _DECLARATION_START_PATTERN.match(contents, cursor)
        if match is None:
            raise DeclarationParseError(
                f"{file_path} must contain only {expected_kind}(...) declarations"
            )
        actual_kind: str = match.group("kind")
        if actual_kind != expected_kind:
            raise DeclarationParseError(
                f"{file_path} contains {actual_kind}(...) under the {expected_kind.lower()}s root"
            )
        open_index: int = match.end() - 1
        close_index: int = _find_closing_parenthesis(
            contents=contents,
            open_index=open_index,
            file_path=file_path,
        )
        cursor = _skip_whitespace(contents=contents, start=close_index + 1)
        if cursor >= len(contents) or contents[cursor] != _STATEMENT_TERMINATOR:
            raise DeclarationParseError(f"{expected_kind}(...) in '{file_path}' must end with ';'")
        try:
            header: str = contents[open_index + 1 : close_index]
            headers.append(
                _ParsedDeclarationHeader(
                    values=parse_header_values(
                        header=header,
                        file_path=file_path,
                        statement_name=expected_kind,
                    ),
                    header=header,
                    header_start=open_index + 1,
                )
            )
        except ModelSqlParseError as error:
            raise DeclarationParseError(str(error)) from error
        cursor += 1
    if not headers:
        raise DeclarationParseError(f"{file_path} contains no {expected_kind}(...) declarations")
    return tuple(headers)


def _parse_enum_declaration(
    *,
    values: dict[str, object],
    file_path: Path,
    relative_path: Path,
    model_name: str | None,
) -> EnumDeclaration:
    unknown_keys: set[str] = set(values) - {"name", "members"}
    if unknown_keys:
        raise DeclarationParseError(
            f"{file_path} enum has unknown keys: {', '.join(sorted(unknown_keys))}"
        )
    name: str = _parse_declaration_name(
        raw_name=values.get("name"),
        file_path=file_path,
        kind="enum",
        model_name=model_name,
    )
    raw_members: object | None = values.get("members")
    members: tuple[EnumMember, ...]
    if isinstance(raw_members, list):
        members = _parse_shorthand_members(
            raw_members=raw_members,
            file_path=file_path,
            enum_name=name,
        )
    elif isinstance(raw_members, dict):
        members = _parse_explicit_members(
            raw_members=cast(dict[object, object], raw_members),
            file_path=file_path,
            enum_name=name,
        )
    else:
        raise DeclarationParseError(f"{file_path} enum '{name}' members must use [...] or (...)")
    if not members:
        raise DeclarationParseError(f"{file_path} enum '{name}' must declare at least one member")
    invalid_member: EnumMember | None = next(
        (member for member in members if member.name != member.name.upper()),
        None,
    )
    if invalid_member is not None:
        raise DeclarationParseError(
            f"{file_path} enum '{name}' member identifiers must be uppercase: "
            f"'{invalid_member.name}'"
        )
    member_types: set[type[object]] = {type(member.value) for member in members}
    if len(member_types) != 1:
        raise DeclarationParseError(
            f"{file_path} enum '{name}' members must use one consistent scalar type"
        )
    return EnumDeclaration(
        name=name,
        members=members,
        scalar_type=_scalar_type(value=members[0].value),
        relative_path=relative_path,
        model_name=model_name,
    )


def _parse_shorthand_members(
    *, raw_members: Sequence[object], file_path: Path, enum_name: str
) -> tuple[EnumMember, ...]:
    members: list[EnumMember] = []
    seen_names: set[str] = set()
    raw_member: object
    for raw_member in raw_members:
        if not isinstance(raw_member, str) or not _IDENTIFIER_PATTERN.fullmatch(raw_member):
            raise DeclarationParseError(
                f"{file_path} enum '{enum_name}' shorthand members must be identifiers"
            )
        if raw_member in seen_names:
            raise DeclarationParseError(
                f"{file_path} enum '{enum_name}' has duplicate member '{raw_member}'"
            )
        seen_names.add(raw_member)
        members.append(EnumMember(name=raw_member, value=raw_member))
    return tuple(members)


def _parse_explicit_members(
    *, raw_members: dict[object, object], file_path: Path, enum_name: str
) -> tuple[EnumMember, ...]:
    members: list[EnumMember] = []
    raw_name: object
    raw_value: object
    for raw_name, raw_value in raw_members.items():
        member_name: str = _parse_identifier(
            raw_value=raw_name,
            file_path=file_path,
            label=f"enum '{enum_name}' member",
        )
        scalar_value: str | int = _parse_scalar(
            raw_value=raw_value,
            file_path=file_path,
            label=f"enum '{enum_name}' member '{member_name}'",
        )
        members.append(EnumMember(name=member_name, value=scalar_value))
    return tuple(members)


def _parse_constant_declaration(
    *,
    name: object | None,
    value: object | None,
    explicit_type: object | None,
    raw_render_as: object | None,
    file_path: Path,
    relative_path: Path,
    model_name: str | None,
    unknown_keys: set[str],
) -> ConstantDeclaration:
    if unknown_keys:
        raise DeclarationParseError(
            f"{file_path} constant has unknown keys: {', '.join(sorted(unknown_keys))}"
        )
    parsed_name: str = _parse_declaration_name(
        raw_name=name,
        file_path=file_path,
        kind="constant",
        model_name=model_name,
    )
    if isinstance(value, AuthoredSqlValueCall):
        if explicit_type is not MISSING_SQL_VALUE or raw_render_as is not MISSING_SQL_VALUE:
            raise DeclarationParseError(
                f"{file_path} constant '{parsed_name}' cannot combine wrapper and outer options"
            )
        wrapper_values: dict[str, object] = dict(value.arguments)
        wrapper_unknown_keys: set[str] = set(wrapper_values) - {"value", "type", "render_as"}
        if wrapper_unknown_keys:
            raise DeclarationParseError(
                f"{file_path} constant '{parsed_name}' wrapper has unknown keys: "
                f"{', '.join(sorted(wrapper_unknown_keys))}"
            )
        value = wrapper_values.get("value", MISSING_SQL_VALUE)
        explicit_type = wrapper_values.get("type", MISSING_SQL_VALUE)
        raw_render_as = wrapper_values.get("render_as", MISSING_SQL_VALUE)
    if value is MISSING_SQL_VALUE:
        raise DeclarationParseError(
            f"{file_path} constant '{parsed_name}' is missing required value"
        )
    parsed_explicit_type: str | None = _parse_constant_option(
        raw_value=explicit_type,
        file_path=file_path,
        label=f"constant '{parsed_name}' type",
    )
    render_as_text: str | None = _parse_constant_option(
        raw_value=raw_render_as,
        file_path=file_path,
        label=f"constant '{parsed_name}' render_as",
    )
    try:
        render_as: CollectionRendering | None = (
            CollectionRendering(render_as_text) if render_as_text is not None else None
        )
    except ValueError as error:
        raise DeclarationParseError(
            f"{file_path} constant '{parsed_name}' render_as must be value_list or array"
        ) from error
    try:
        typed_value: SqlValue = normalize_sql_value(
            raw_value=value,
            explicit_type=parsed_explicit_type,
            context=f"{file_path} constant '{parsed_name}'",
        )
    except SqlValueValidationError as error:
        raise DeclarationParseError(str(error)) from error
    if render_as is not None and typed_value.kind not in {SqlValueKind.LIST, SqlValueKind.SET}:
        raise DeclarationParseError(
            f"{file_path} constant '{parsed_name}' is {typed_value.kind.value} and does not "
            "support "
            f"render_as {render_as.value}"
        )
    return ConstantDeclaration(
        name=parsed_name,
        value=typed_value,
        relative_path=relative_path,
        model_name=model_name,
        render_as=render_as,
    )


def _parse_constant_option(*, raw_value: object, file_path: Path, label: str) -> str | None:
    if raw_value is MISSING_SQL_VALUE:
        return None
    if not isinstance(raw_value, str) or not raw_value:
        raise DeclarationParseError(f"{file_path} {label} must be an identifier")
    return raw_value


def _parse_declaration_name(
    *, raw_name: object | None, file_path: Path, kind: str, model_name: str | None
) -> str:
    name: str = _parse_identifier(raw_value=raw_name, file_path=file_path, label=kind)
    if model_name is None and name.startswith("_"):
        raise DeclarationParseError(f"{file_path} public {kind} '{name}' must not start with '_'")
    if model_name is not None and not name.startswith("_"):
        raise DeclarationParseError(f"{file_path} model-local {kind} '{name}' must start with '_'")
    return name


def _parse_identifier(*, raw_value: object | None, file_path: Path, label: str) -> str:
    if not isinstance(raw_value, str) or not _IDENTIFIER_PATTERN.fullmatch(raw_value):
        raise DeclarationParseError(f"{file_path} {label} name must be a SQL identifier")
    return raw_value


def _parse_scalar(*, raw_value: object | None, file_path: Path, label: str) -> str | int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, str | int):
        raise DeclarationParseError(f"{file_path} {label} value must be a string or integer")
    return raw_value


def _scalar_type(*, value: str | int) -> str:
    return _VARCHAR_TYPE if isinstance(value, str) else _INTEGER_TYPE


def _find_closing_parenthesis(*, contents: str, open_index: int, file_path: Path) -> int:
    depth: int = 1
    quote: str | None = None
    index: int = open_index + 1
    while index < len(contents):
        character: str = contents[index]
        if quote is not None:
            if character == _ESCAPE_CHARACTER:
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in _QUOTE_TOKENS:
            quote = character
        elif character == _OPEN_PARENTHESIS:
            depth += 1
        elif character == _CLOSE_PARENTHESIS:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise DeclarationParseError(f"{file_path} has an unterminated declaration header")


def _skip_whitespace(*, contents: str, start: int) -> int:
    index: int = start
    while index < len(contents) and contents[index].isspace():
        index += 1
    return index
