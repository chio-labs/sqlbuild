"""Parsing helpers for authored SQL hook resources."""

from __future__ import annotations

from inspect import cleandoc
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SqlHookParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlHookFile
from sqlbuild.compiler.sql_hooks.main._validate_statement import validate_sql_hook_statement

_SUPPORTED_HOOK_HEADER_KEYS: frozenset[str] = frozenset({"description"})
_SQL_ESCAPE_CHARACTER: str = "\\"
_SQL_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"', "`"})
_SQL_STATEMENT_TERMINATOR: str = ";"
_HOOK_HEADER_OPEN: str = "("
_HOOK_HEADER_CLOSE: str = ")"


def parse_sql_hook_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlHookFile:
    """Parse exactly one named SQL hook resource from a file."""

    header: str
    raw_sql_body: str
    header, raw_sql_body = _split_hook_file(contents=contents, file_path=file_path)
    header_values: dict[str, object] = _parse_hook_header(header=header, file_path=file_path)
    sql_body: str = cleandoc(raw_sql_body)
    if not sql_body:
        raise SqlHookParseError(f"SQL hook '{file_path}' must define SQL after HOOK(...)")
    validate_sql_hook_statement(sql=sql_body, file_path=file_path)
    description_value: object | None = header_values.get("description")
    return DiscoveredSqlHookFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        header_values=header_values,
        sql_body=sql_body,
        name=file_path.stem,
        description=cast(str | None, description_value),
    )


def _split_hook_file(*, contents: str, file_path: Path) -> tuple[str, str]:
    index: int = 0
    while index < len(contents) and contents[index].isspace():
        index += 1
    if not contents.startswith("HOOK", index):
        raise SqlHookParseError(
            f"SQL hook '{file_path}' must start with a HOOK() header as the first "
            "non-whitespace content"
        )
    index += len("HOOK")
    while index < len(contents) and contents[index].isspace():
        index += 1
    if index >= len(contents) or contents[index] != _HOOK_HEADER_OPEN:
        raise SqlHookParseError(f"SQL hook '{file_path}' must define a HOOK(...) header")

    header_start: int = index + 1
    depth: int = 1
    quote: str | None = None
    index = header_start
    while index < len(contents):
        character: str = contents[index]
        if quote is not None:
            if character == _SQL_ESCAPE_CHARACTER:
                index += 2
                continue
            if character == quote:
                if index + 1 < len(contents) and contents[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in _SQL_QUOTE_CHARACTERS:
            quote = character
        elif character == _HOOK_HEADER_OPEN:
            depth += 1
        elif character == _HOOK_HEADER_CLOSE:
            depth -= 1
            if depth == 0:
                break
        index += 1
    if depth != 0:
        raise SqlHookParseError(f"SQL hook '{file_path}' has an unterminated HOOK(...) header")

    header_end: int = index
    index += 1
    while index < len(contents) and contents[index].isspace():
        index += 1
    if index >= len(contents) or contents[index] != _SQL_STATEMENT_TERMINATOR:
        raise SqlHookParseError(f"SQL hook '{file_path}' HOOK(...) header must end with ';'")
    return contents[header_start:header_end], contents[index + 1 :]


def _parse_hook_header(*, header: str, file_path: Path) -> dict[str, object]:
    stripped_header: str = header.strip()
    if not stripped_header:
        return {}
    try:
        parsed_header: object = yaml.safe_load(f"{{{stripped_header}}}")
    except YAMLError as error:
        raise SqlHookParseError(
            f"HOOK() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise SqlHookParseError(
            f"HOOK() header in '{file_path}' must be a mapping like `HOOK (description: \"...\");`"
        )
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in _SUPPORTED_HOOK_HEADER_KEYS
    )
    if unsupported_keys:
        raise SqlHookParseError(
            f"HOOK() in '{file_path}' has unsupported keys: {', '.join(unsupported_keys)}"
        )
    description: object | None = parsed_header.get("description")
    if description is not None and (not isinstance(description, str) or not description.strip()):
        raise SqlHookParseError(f"HOOK() description in '{file_path}' must be a non-empty string")
    return cast(dict[str, object], parsed_header)
