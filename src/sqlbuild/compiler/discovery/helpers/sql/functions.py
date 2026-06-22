"""Parsing helpers for authored SQL function files."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from sqlbuild.compiler.discovery.helpers.sql.constants import FUNCTION_HEADER_PATTERN
from sqlbuild.compiler.discovery.helpers.sql.model_files import _parse_model_header


def parse_function_sql(contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse a raw SQL function file into header values and SQL body."""

    header_match: re.Match[str] | None = FUNCTION_HEADER_PATTERN.match(contents)
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
