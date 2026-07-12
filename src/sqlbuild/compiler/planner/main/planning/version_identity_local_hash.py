"""Public entrypoint for local model version identity hashing."""

from __future__ import annotations

from sqlbuild.compiler.planner.helpers.identity.hashing import (
    build_model_local_identity_hash as _build_model_local_identity_hash,
)


def build_model_local_identity_hash(*, query_sql: str, metadata_json: str) -> str:
    """Build a model's local identity hash from query SQL and non-query metadata."""

    return _build_model_local_identity_hash(query_sql=query_sql, metadata_json=metadata_json)
