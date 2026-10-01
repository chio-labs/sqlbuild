"""Query fingerprint normalization and hashing."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.compiler.fingerprints.constants import (
    GENERIC_FINGERPRINT_DIALECT,
    QUERY_FINGERPRINT_CACHE_SIZE,
    SQL_FUNCTION_LANGUAGE,
)
from sqlbuild.compiler.fingerprints.exceptions import QueryFingerprintError
from sqlbuild.compiler.sql_analysis.constants import NATIVE_DIALECT_ALIASES

_WHITESPACE_RUN: re.Pattern[str] = re.compile(r"\s+")


def normalize_query_sql_impl(query_sql: str) -> str:
    """Normalize query SQL text by collapsing whitespace runs."""

    stripped: str = query_sql.strip()
    return _WHITESPACE_RUN.sub(" ", stripped)


def compute_query_hash_impl(*, query_sql: str, dialect: str | None) -> str:
    """Compute the persisted SHA-256 fingerprint of the query's canonical token stream."""

    native_dialect: str = (
        NATIVE_DIALECT_ALIASES.get(dialect, dialect) if dialect else GENERIC_FINGERPRINT_DIALECT
    )
    return _cached_query_hash(query_sql=query_sql, dialect=native_dialect)


def compute_function_definition_hash_impl(
    *, fingerprint_sql: str, language: str, dialect: str | None
) -> str:
    """Fingerprint SQL function definitions like queries and other languages exactly."""

    if language == SQL_FUNCTION_LANGUAGE:
        return compute_query_hash_impl(query_sql=fingerprint_sql, dialect=dialect)
    return hashlib.sha256(fingerprint_sql.encode("utf-8")).hexdigest()


@lru_cache(maxsize=QUERY_FINGERPRINT_CACHE_SIZE)
def _cached_query_hash(*, query_sql: str, dialect: str) -> str:
    try:
        return _native.query_fingerprint(query_sql, dialect)
    except ValueError as error:
        raise QueryFingerprintError(str(error)) from None
