"""Query SQL fingerprint normalization entrypoint."""

from sqlbuild.compiler.fingerprints.helpers.query import normalize_query_sql_impl


def normalize_query_sql(query_sql: str) -> str:
    """Normalize query SQL while preserving persisted hash behavior."""

    return normalize_query_sql_impl(query_sql)
