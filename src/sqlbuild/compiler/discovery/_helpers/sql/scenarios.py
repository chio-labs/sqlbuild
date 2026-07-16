"""Parsing helpers for authored SQL scenario files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SqlScenarioParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile

_SCENARIO_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SCENARIO\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)


def parse_sql_scenario_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlScenarioFile:
    """Parse one SQL-native scenario file."""

    header_match: re.Match[str] | None = _SCENARIO_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise SqlScenarioParseError(
            f"SQL scenario '{file_path}' must start with a SCENARIO() header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_scenario_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    sql_body: str = cleandoc(header_match.group("sql"))
    if not sql_body:
        raise SqlScenarioParseError(
            f"SQL scenario '{file_path}' must define SQL after SCENARIO(...)"
        )

    return DiscoveredSqlScenarioFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        header_values=header_values,
        sql_body=sql_body,
        name=file_path.stem,
    )


def _parse_scenario_header(*, header: str, file_path: Path) -> dict[str, object]:
    stripped_header: str = header.strip()
    if not stripped_header:
        return {}

    try:
        parsed_header: object = yaml.safe_load(f"{{{stripped_header}}}")
    except YAMLError as error:
        raise SqlScenarioParseError(
            f"SCENARIO() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise SqlScenarioParseError(
            f"SCENARIO() header in '{file_path}' must be a mapping like "
            '`SCENARIO (description: "...");`'
        )

    supported_keys: set[str] = {"description", "tags"}
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in supported_keys
    )
    if unsupported_keys:
        raise SqlScenarioParseError(
            f"SCENARIO() in '{file_path}' only supports `description` and `tags` right now; "
            f"unsupported keys: {', '.join(unsupported_keys)}"
        )

    description_value: object | None = parsed_header.get("description")
    if description_value is not None and not isinstance(description_value, str):
        raise SqlScenarioParseError(f"SCENARIO() description in '{file_path}' must be a string")
    tags_value: object | None = parsed_header.get("tags")
    if tags_value is not None and (
        not isinstance(tags_value, list) or not all(isinstance(tag, str) for tag in tags_value)
    ):
        raise SqlScenarioParseError(f"SCENARIO() tags in '{file_path}' must be a list of strings")

    return cast(dict[str, object], parsed_header)
