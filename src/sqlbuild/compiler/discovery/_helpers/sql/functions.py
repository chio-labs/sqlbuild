"""Parsing helpers for authored SQL function files."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.model_files import _parse_model_header
from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError

_FUNCTION_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*FUNCTION\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)


def parse_function_sql(*, contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse a raw SQL function file into header values and SQL body."""

    header_match: re.Match[str] | None = _FUNCTION_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise ModelSqlParseError(
            f"SQL function '{file_path}' must start with a FUNCTION(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_model_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    body_sql: str = header_match.group("sql").strip()
    if not body_sql:
        raise ModelSqlParseError(f"SQL function '{file_path}' must contain SQL after FUNCTION(...)")
    return header_values, body_sql
