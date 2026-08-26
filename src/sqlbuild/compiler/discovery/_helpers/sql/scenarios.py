"""Parsing helpers for authored SQL scenario files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.model_files import parse_header_values
from sqlbuild.compiler.discovery.constants import SQL_SCENARIOS_OWNERSHIP_ROOT
from sqlbuild.compiler.discovery.exceptions import SqlScenarioParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile

_SCENARIO_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SCENARIO\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
_SCENARIO_DESCRIPTION_HEADER_KEY: str = "description"
_SCENARIO_TAGS_HEADER_KEY: str = "tags"


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
        ownership_root=Path(SQL_SCENARIOS_OWNERSHIP_ROOT),
    )


def _parse_scenario_header(*, header: str, file_path: Path) -> dict[str, object]:
    parsed_header: dict[str, object] = parse_header_values(
        header=header,
        file_path=file_path,
        statement_name="SCENARIO",
        error_class=SqlScenarioParseError,
    )

    supported_keys: set[str] = {
        _SCENARIO_DESCRIPTION_HEADER_KEY,
        _SCENARIO_TAGS_HEADER_KEY,
    }
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in supported_keys
    )
    if unsupported_keys:
        raise SqlScenarioParseError(
            f"SCENARIO() in '{file_path}' only supports `description` and `tags` right now; "
            f"unsupported keys: {', '.join(unsupported_keys)}"
        )

    description_value: object | None = parsed_header.get(_SCENARIO_DESCRIPTION_HEADER_KEY)
    if _SCENARIO_DESCRIPTION_HEADER_KEY in parsed_header and not isinstance(description_value, str):
        raise SqlScenarioParseError(f"SCENARIO() description in '{file_path}' must be a string")
    tags_value: object | None = parsed_header.get(_SCENARIO_TAGS_HEADER_KEY)
    if _SCENARIO_TAGS_HEADER_KEY in parsed_header and (
        not isinstance(tags_value, list) or not all(isinstance(tag, str) for tag in tags_value)
    ):
        raise SqlScenarioParseError(f"SCENARIO() tags in '{file_path}' must be a list of strings")

    return parsed_header
