"""Parsing helpers for authored SQL hook resources."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SqlHookParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlHookFile

_HOOK_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*HOOK\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
_HOOK_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*HOOK\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)
_SUPPORTED_HOOK_HEADER_KEYS: frozenset[str] = frozenset({"description"})


def parse_sql_hook_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlHookFile:
    """Parse exactly one named SQL hook resource from a file."""

    header_matches: tuple[re.Match[str], ...] = tuple(_HOOK_HEADER_ONLY_PATTERN.finditer(contents))
    if not header_matches or contents[: header_matches[0].start()].strip():
        raise SqlHookParseError(
            f"SQL hook '{file_path}' must start with a HOOK() header as the first "
            "non-whitespace content"
        )
    if len(header_matches) != 1:
        raise SqlHookParseError(f"SQL hook '{file_path}' must contain exactly one HOOK(...) block")

    header_match: re.Match[str] | None = _HOOK_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise SqlHookParseError(f"SQL hook '{file_path}' must contain exactly one HOOK(...) block")
    header_values: dict[str, object] = _parse_hook_header(
        header=header_match.group("header"), file_path=file_path
    )
    sql_body: str = cleandoc(header_match.group("sql"))
    if not sql_body:
        raise SqlHookParseError(f"SQL hook '{file_path}' must define SQL after HOOK(...)")
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
