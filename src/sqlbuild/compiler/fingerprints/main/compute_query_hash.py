"""Query fingerprint computation entrypoint."""

from sqlbuild.compiler.fingerprints._helpers.query import compute_query_hash_impl


def compute_query_hash(query_sql: str) -> str:
    """Compute the persisted SHA-256 query fingerprint."""

    return compute_query_hash_impl(query_sql)
