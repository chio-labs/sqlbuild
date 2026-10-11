"""Query fingerprint normalization and hashing, computed natively."""

from __future__ import annotations

from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.compiler.fingerprints.constants import QUERY_FINGERPRINT_CACHE_SIZE
from sqlbuild.compiler.fingerprints.exceptions import QueryFingerprintError


def normalize_query_sql_impl(query_sql: str) -> str:
    """Normalize query SQL text by collapsing whitespace runs."""

    return _native.normalize_query_text(query_sql)


def compute_query_hash_impl(*, query_sql: str, dialect: str | None) -> str:
    """Compute the persisted SHA-256 fingerprint of the query's canonical token stream."""

    return _cached_query_hash(query_sql=query_sql, dialect=dialect)


def compute_function_definition_hash_impl(
    *, fingerprint_sql: str, language: str, dialect: str | None
) -> str:
    """Fingerprint SQL function definitions like queries and other languages exactly."""

    try:
        return _native.function_definition_hash(fingerprint_sql, language, dialect)
    except ValueError as error:
        raise QueryFingerprintError(str(error)) from None


@lru_cache(maxsize=QUERY_FINGERPRINT_CACHE_SIZE)
def _cached_query_hash(*, query_sql: str, dialect: str | None) -> str:
    try:
        return _native.compiler_query_hash(query_sql, dialect)
    except ValueError as error:
        raise QueryFingerprintError(str(error)) from None
