"""Hash computation for query and schema fingerprints."""

from __future__ import annotations

import hashlib
import re

from sqlbuild.adapter.shared.models import ColumnInfo

_WHITESPACE_RUN: re.Pattern[str] = re.compile(r"\s+")


def normalize_query_sql(query_sql: str) -> str:
    """Normalize query SQL for stable hashing."""

    stripped: str = query_sql.strip()
    return _WHITESPACE_RUN.sub(" ", stripped)


def compute_query_hash(query_sql: str) -> str:
    """Compute a stable hash of query SQL after normalization."""

    normalized: str = normalize_query_sql(query_sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_schema_fingerprint(columns: tuple[ColumnInfo, ...]) -> str:
    """Compute a stable hash from an ordered column schema."""

    parts: list[str] = [f"{col.name}:{col.type}" for col in columns]
    joined: str = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
