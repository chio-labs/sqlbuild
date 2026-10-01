"""Query fingerprint computation entrypoint."""

from sqlbuild.compiler.fingerprints._helpers.query import compute_query_hash_impl


def compute_query_hash(*, query_sql: str, dialect: str | None) -> str:
    """Fingerprint query SQL, ignoring layout, comments and keyword case."""

    return compute_query_hash_impl(query_sql=query_sql, dialect=dialect)
