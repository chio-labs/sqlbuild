"""Parsing helpers for authored SQL scenario files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.header_keys import reject_unsupported_header_keys
from sqlbuild.compiler.discovery._helpers.sql.model_files import parse_header_values
from sqlbuild.compiler.discovery.constants import (
    SQL_SCENARIOS_OWNERSHIP_ROOT,
    STATEMENT_HEADER_BODY_PATTERN,
)
from sqlbuild.compiler.discovery.exceptions import SqlScenarioParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile

_SCENARIO_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SCENARIO\s*\(" + STATEMENT_HEADER_BODY_PATTERN + r"\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
_SCENARIO_DESCRIPTION_HEADER_KEY: str = "description"
_SCENARIO_TAGS_HEADER_KEY: str = "tags"
_SCENARIO_HEADER_KEYS: frozenset[str] = frozenset(
    {_SCENARIO_DESCRIPTION_HEADER_KEY, _SCENARIO_TAGS_HEADER_KEY}
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
        header_line=contents.count("\n", 0, header_match.start("header")) + 1,
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


def _parse_scenario_header(*, header: str, header_line: int, file_path: Path) -> dict[str, object]:
    parsed_header: dict[str, object] = parse_header_values(
        header=header,
        file_path=file_path,
        statement_name="SCENARIO",
        error_class=SqlScenarioParseError,
    )

    reject_unsupported_header_keys(
        header_values=parsed_header,
        supported_keys=_SCENARIO_HEADER_KEYS,
        statement="SCENARIO()",
        header=header,
        header_line=header_line,
        file_path=file_path,
        error_class=SqlScenarioParseError,
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
