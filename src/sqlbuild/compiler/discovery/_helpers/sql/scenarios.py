"""Parsing helpers for authored SQL scenario files."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.constants import (
    SQL_SCENARIOS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.discovery.exceptions import SqlScenarioParseError
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile

_SCENARIO_DESCRIPTION_HEADER_KEY: str = "description"
_SCENARIO_TAGS_HEADER_KEY: str = "tags"


def build_sql_scenario_file(
    *,
    header_values: dict[str, object],
    sql_body: str,
    contents: str,
    file_path: Path,
    relative_path: Path,
    sql_body_span: tuple[int, int] | None = None,
) -> DiscoveredSqlScenarioFile:
    """Validate a header-parsed SCENARIO file with only supported keys and build its record."""

    description_value: object | None = header_values.get(_SCENARIO_DESCRIPTION_HEADER_KEY)
    if _SCENARIO_DESCRIPTION_HEADER_KEY in header_values and not isinstance(description_value, str):
        raise SqlScenarioParseError(f"SCENARIO() description in '{file_path}' must be a string")
    tags_value: object | None = header_values.get(_SCENARIO_TAGS_HEADER_KEY)
    if _SCENARIO_TAGS_HEADER_KEY in header_values and (
        not isinstance(tags_value, list) or not all(isinstance(tag, str) for tag in tags_value)
    ):
        raise SqlScenarioParseError(f"SCENARIO() tags in '{file_path}' must be a list of strings")
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
        sql_body_span=sql_body_span,
        name=file_path.stem,
        ownership_root=Path(SQL_SCENARIOS_OWNERSHIP_ROOT),
    )
