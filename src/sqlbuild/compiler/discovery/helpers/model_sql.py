"""Parsing helpers for authored SQL model files."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from sqlbuild.compiler.discovery.helpers.constants import MODEL_HEADER_PATTERN


def parse_model_sql(contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse a raw SQL model file into header values and SQL body."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise ModelSqlParseError(
            f"SQL model '{file_path}' must start with a MODEL(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_model_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    query: str = header_match.group("sql").strip()
    if not query:
        raise ModelSqlParseError(f"SQL model '{file_path}' must contain SQL after MODEL(...)")
    return header_values, query


def _parse_model_header(*, header: str, file_path: Path) -> dict[str, object]:
    normalized_header: str = _normalize_model_header_yaml(header)
    try:
        parsed_header: object = yaml.safe_load(normalized_header)
    except YAMLError as error:
        raise ModelSqlParseError(
            f"MODEL(...) in '{file_path}' contains invalid YAML: {error}"
        ) from error
    if parsed_header is None:
        return {}
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise ModelSqlParseError(
            f"MODEL(...) in '{file_path}' must define a mapping of key: value pairs"
        )
    return cast(dict[str, object], parsed_header)


def _normalize_model_header_yaml(header: str) -> str:
    """Normalize SQL-style header syntax into YAML block mapping text."""

    normalized_header: str = dedent(header).strip()
    return re.sub(r",(?=\s*(?:\n|$))", "", normalized_header)
