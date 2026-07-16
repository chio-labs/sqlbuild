"""Query fingerprint normalization and hashing."""

from __future__ import annotations

import hashlib
import re

_WHITESPACE_RUN: re.Pattern[str] = re.compile(r"\s+")


def normalize_query_sql_impl(query_sql: str) -> str:
    """Normalize query SQL while preserving persisted hash behavior."""

    stripped: str = query_sql.strip()
    return _WHITESPACE_RUN.sub(" ", stripped)


def compute_query_hash_impl(query_sql: str) -> str:
    """Compute the persisted SHA-256 query fingerprint."""

    normalized: str = normalize_query_sql_impl(query_sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
