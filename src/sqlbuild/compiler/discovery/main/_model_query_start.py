"""Locate a model's discovered query SQL within its authored file."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.sql.model_files import match_model_header
from sqlbuild.compiler.discovery.models import ModelHeaderMatch


def get_model_query_start(*, contents: str, query_sql: str) -> int | None:
    """Return where discovery's stripped query SQL starts after the MODEL header, if it does."""

    header_match: ModelHeaderMatch | None = match_model_header(contents)
    if header_match is None:
        return None
    sql: str = header_match.sql
    start: int = header_match.sql_start + len(sql) - len(sql.lstrip())
    return start if contents.startswith(query_sql, start) else None
