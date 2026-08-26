"""Parsing helpers for authored SQL-native test files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery._helpers.sql.model_files import parse_header_values
from sqlbuild.compiler.discovery.exceptions import SqlTestParseError
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestCase,
    SqlTestParameterDeclaration,
)
from sqlbuild.sql_values.exceptions import SqlValueValidationError
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind

_TEST_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
_TEST_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)
_TEST_NAME_HEADER_KEY: str = "name"
_TEST_MODE_HEADER_KEY: str = "mode"
_TEST_PARAMETERS_HEADER_KEY: str = "parameters"
_TEST_CASES_HEADER_KEY: str = "cases"
_PARAMETER_TYPES: tuple[SqlValueKind, ...] = (
    SqlValueKind.STRING,
    SqlValueKind.INTEGER,
    SqlValueKind.BOOLEAN,
    SqlValueKind.FLOAT,
    SqlValueKind.DECIMAL,
)
_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_sql_test_file(*, contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse one SQL-native test file into one or more raw TEST(...) blocks."""

    raw_test_blocks: tuple[str, ...] = _split_sql_test_blocks(
        file_path=file_path, contents=contents
    )
    if not raw_test_blocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    discovered_blocks: list[DiscoveredSqlTestBlock] = []
    test_index: int
    raw_test_block: str
    for test_index, raw_test_block in enumerate(raw_test_blocks, start=1):
        discovered_blocks.append(
            _parse_single_sql_test_block(
                file_path=file_path,
                raw_test_block=raw_test_block,
                test_index=test_index,
            )
        )

    _validate_test_names(file_path=file_path, blocks=tuple(discovered_blocks))
    return tuple(discovered_blocks)


def _split_sql_test_blocks(*, file_path: Path, contents: str) -> tuple[str, ...]:
    matches: tuple[re.Match[str], ...] = tuple(_TEST_HEADER_ONLY_PATTERN.finditer(contents))
    if not matches:
        return ()
    if contents[: matches[0].start()].strip():
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    raw_blocks: list[str] = []
    match_index: int
    match: re.Match[str]
    for match_index, match in enumerate(matches):
        next_start: int = (
            matches[match_index + 1].start() if match_index + 1 < len(matches) else len(contents)
        )
        raw_blocks.append(contents[match.start() : next_start].strip())
    return tuple(raw_blocks)


def _parse_single_sql_test_block(
    *,
    file_path: Path,
    raw_test_block: str,
    test_index: int,
) -> DiscoveredSqlTestBlock:
    header_match: re.Match[str] | None = _TEST_HEADER_PATTERN.match(raw_test_block)
    if header_match is None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_test_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    sql_body: str = cleandoc(header_match.group("sql"))
    if not sql_body:
        raise SqlTestParseError(f"SQL test '{file_path}' must define SQL after TEST(...)")

    name_value: object | None = header_values.get("name")
    test_name: str | None = cast(str | None, name_value)
    mode_value: object = header_values.get("mode", DEFAULT_SQL_TEST_MODE.value)
    test_mode: SqlTestMode = SqlTestMode(str(mode_value))
    parameters, cases = _parse_test_parameters_and_cases(
        header_values=header_values,
        file_path=file_path,
    )
    return DiscoveredSqlTestBlock(
        test_index=test_index,
        header_values=header_values,
        sql_body=sql_body,
        name=test_name,
        mode=test_mode,
        parameters=parameters,
        cases=cases,
    )


def _parse_test_header(*, header: str, file_path: Path) -> dict[str, object]:
    parsed_header: dict[str, object] = parse_header_values(
        header=header,
        file_path=file_path,
        statement_name="TEST",
        error_class=SqlTestParseError,
    )

    supported_keys: frozenset[str] = frozenset(
        {
            _TEST_NAME_HEADER_KEY,
            _TEST_MODE_HEADER_KEY,
            _TEST_PARAMETERS_HEADER_KEY,
            _TEST_CASES_HEADER_KEY,
        }
    )
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in supported_keys
    )
    if unsupported_keys:
        raise SqlTestParseError(
            f"TEST() in '{file_path}' only supports `name`, `mode`, `parameters`, and "
            "`cases`; unsupported keys: "
            f"{', '.join(unsupported_keys)}"
        )

    if _TEST_NAME_HEADER_KEY in parsed_header:
        _validate_test_name(name_value=parsed_header[_TEST_NAME_HEADER_KEY], file_path=file_path)
    if _TEST_MODE_HEADER_KEY in parsed_header:
        _validate_test_mode(mode_value=parsed_header[_TEST_MODE_HEADER_KEY], file_path=file_path)

    return parsed_header


def _parse_test_parameters_and_cases(
    *, header_values: dict[str, object], file_path: Path
) -> tuple[tuple[SqlTestParameterDeclaration, ...], tuple[DiscoveredSqlTestCase, ...]]:
    raw_parameters: object | None = header_values.get(_TEST_PARAMETERS_HEADER_KEY)
    raw_cases: object | None = header_values.get(_TEST_CASES_HEADER_KEY)
    if raw_parameters is None and raw_cases is None:
        return (), ()
    if raw_parameters is None or raw_cases is None:
        raise SqlTestParseError(
            f"TEST() in '{file_path}' must define `parameters` and `cases` together"
        )
    if not isinstance(raw_parameters, dict) or not raw_parameters:
        raise SqlTestParseError(f"TEST() parameters in '{file_path}' must be a non-empty mapping")
    if not isinstance(raw_cases, dict) or not raw_cases:
        raise SqlTestParseError(f"TEST() cases in '{file_path}' must be a non-empty mapping")

    parameters: tuple[SqlTestParameterDeclaration, ...] = tuple(
        _parse_parameter_declaration(
            name=name,
            raw_declaration=raw_declaration,
            file_path=file_path,
        )
        for name, raw_declaration in cast(dict[object, object], raw_parameters).items()
    )
    parameter_names: tuple[str, ...] = tuple(parameter.name for parameter in parameters)
    cases: tuple[DiscoveredSqlTestCase, ...] = tuple(
        _parse_test_case(
            name=name,
            raw_values=raw_values,
            case_index=case_index,
            parameters=parameters,
            parameter_names=parameter_names,
            file_path=file_path,
        )
        for case_index, (name, raw_values) in enumerate(
            cast(dict[object, object], raw_cases).items()
        )
    )
    return parameters, cases


def _parse_parameter_declaration(
    *, name: object, raw_declaration: object, file_path: Path
) -> SqlTestParameterDeclaration:
    parameter_name: str = _parse_test_identifier(value=name, label="parameter", file_path=file_path)
    nullable: bool = False
    raw_type: object = raw_declaration
    if isinstance(raw_declaration, dict):
        declaration_options: dict[object, object] = cast(dict[object, object], raw_declaration)
        unknown_options: set[object] = set(declaration_options) - {"type", "nullable"}
        if unknown_options:
            names: str = ", ".join(sorted(str(option) for option in unknown_options))
            raise SqlTestParseError(
                f"TEST() parameter '{parameter_name}' in '{file_path}' has unsupported "
                f"options: {names}"
            )
        raw_type = declaration_options.get("type")
        raw_nullable: object = declaration_options.get("nullable", False)
        if not isinstance(raw_nullable, bool):
            raise SqlTestParseError(
                f"TEST() parameter '{parameter_name}' nullable option in '{file_path}' "
                "must be boolean"
            )
        nullable = raw_nullable
    if not isinstance(raw_type, str):
        raise SqlTestParseError(
            f"TEST() parameter '{parameter_name}' type in '{file_path}' must be an identifier"
        )
    try:
        value_type: SqlValueKind = SqlValueKind(raw_type.lower())
    except ValueError as error:
        raise SqlTestParseError(
            f"TEST() parameter '{parameter_name}' in '{file_path}' has unsupported "
            f"type '{raw_type}'"
        ) from error
    if value_type not in _PARAMETER_TYPES:
        allowed: str = ", ".join(value.value for value in _PARAMETER_TYPES)
        raise SqlTestParseError(
            f"TEST() parameter '{parameter_name}' in '{file_path}' must use a scalar "
            f"type: {allowed}"
        )
    return SqlTestParameterDeclaration(
        name=parameter_name,
        value_type=value_type,
        nullable=nullable,
    )


def _parse_test_case(
    *,
    name: object,
    raw_values: object,
    case_index: int,
    parameters: tuple[SqlTestParameterDeclaration, ...],
    parameter_names: tuple[str, ...],
    file_path: Path,
) -> DiscoveredSqlTestCase:
    case_name: str = _parse_test_identifier(value=name, label="case", file_path=file_path)
    if not isinstance(raw_values, dict):
        raise SqlTestParseError(
            f"TEST() case '{case_name}' in '{file_path}' must define a parameter mapping"
        )
    values: dict[object, object] = cast(dict[object, object], raw_values)
    missing: tuple[str, ...] = tuple(name for name in parameter_names if name not in values)
    extra: tuple[str, ...] = tuple(str(name) for name in values if name not in parameter_names)
    if missing:
        raise SqlTestParseError(
            f"TEST() case '{case_name}' in '{file_path}' is missing parameters: "
            f"{', '.join(missing)}"
        )
    if extra:
        raise SqlTestParseError(
            f"TEST() case '{case_name}' in '{file_path}' has undeclared parameters: "
            f"{', '.join(extra)}"
        )
    normalized_values: list[tuple[str, SqlValue]] = []
    parameter: SqlTestParameterDeclaration
    for parameter in parameters:
        raw_value: object = values[parameter.name]
        if raw_value is None and not parameter.nullable:
            raise SqlTestParseError(
                f"TEST() case '{case_name}' parameter '{parameter.name}' in '{file_path}' "
                "is not nullable"
            )
        try:
            value: SqlValue = normalize_sql_value(
                raw_value=raw_value,
                explicit_type=None if raw_value is None else parameter.value_type.value,
                context=f"TEST() case '{case_name}' parameter '{parameter.name}' in '{file_path}'",
            )
        except SqlValueValidationError as error:
            raise SqlTestParseError(str(error)) from error
        normalized_values.append((parameter.name, value))
    return DiscoveredSqlTestCase(
        name=case_name,
        values=tuple(normalized_values),
        case_index=case_index,
    )


def _parse_test_identifier(*, value: object, label: str, file_path: Path) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise SqlTestParseError(f"TEST() {label} name in '{file_path}' must be a SQL identifier")
    return value


def _validate_test_name(*, name_value: object, file_path: Path) -> None:
    if not isinstance(name_value, str) or not name_value.strip():
        raise SqlTestParseError(f"TEST() name in '{file_path}' must be a non-empty string")


def _validate_test_mode(*, mode_value: object, file_path: Path) -> None:
    if not isinstance(mode_value, str):
        raise SqlTestParseError(f"TEST() mode in '{file_path}' must be a string")

    allowed_modes: str = ", ".join(mode.value for mode in SqlTestMode)
    if mode_value not in {mode.value for mode in SqlTestMode}:
        raise SqlTestParseError(f"TEST() mode in '{file_path}' must be one of: {allowed_modes}")


def _validate_test_names(*, file_path: Path, blocks: tuple[DiscoveredSqlTestBlock, ...]) -> None:
    if len(blocks) <= 1:
        return

    unnamed_indexes: tuple[int, ...] = tuple(
        block.test_index for block in blocks if block.name is None
    )
    if unnamed_indexes:
        missing_indexes: str = ", ".join(str(index) for index in unnamed_indexes)
        raise SqlTestParseError(
            f"SQL test '{file_path}' contains multiple TEST blocks; every block must define "
            f"a unique `name`. Missing names for blocks: {missing_indexes}"
        )

    seen_names: set[str] = set()
    block: DiscoveredSqlTestBlock
    for block in blocks:
        if block.name is None:
            raise SqlTestParseError(
                f"SQL test '{file_path}' contains multiple TEST blocks; every block must define "
                "a unique `name`"
            )
        if block.name in seen_names:
            raise SqlTestParseError(
                f"SQL test '{file_path}' defines duplicate TEST() name '{block.name}'"
            )
        seen_names.add(block.name)
