"""Hash computation for fingerprint comparison."""

from __future__ import annotations

import hashlib
import re
from importlib import import_module
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo

_WHITESPACE_RUN: re.Pattern[str] = re.compile(r"\s+")


def normalize_query_sql(query_sql: str) -> str:
    """Normalize query SQL for stable hashing.

    Strips leading/trailing whitespace and collapses internal whitespace runs
    to single spaces. Does not alter casing or identifiers.
    """

    stripped: str = query_sql.strip()
    return _WHITESPACE_RUN.sub(" ", stripped)


def compute_query_hash(query_sql: str) -> str:
    """Compute a stable hash of compiled query SQL after normalization."""

    normalized: str = normalize_query_sql(query_sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_ast_hash(query_sql: str) -> str | None:
    """Compute a stable hash from the SQLGlot-normalized AST.

    Returns None if SQLGlot is not available or the SQL cannot be parsed.
    """

    try:
        sqlglot_module: Any = import_module("sqlglot")
    except ImportError:
        return None
    try:
        parsed: Any = sqlglot_module.parse_one(query_sql)
    except Exception:
        return None
    normalized_sql: str = parsed.sql(pretty=False)
    return hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()


def compute_schema_fingerprint(columns: tuple[ColumnInfo, ...]) -> str:
    """Compute a stable hash from an ordered column schema."""

    parts: list[str] = [f"{col.name}:{col.type}" for col in columns]
    joined: str = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
