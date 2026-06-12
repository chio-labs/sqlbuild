"""Shared model version identity hashing helpers."""

from __future__ import annotations

import hashlib

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType


def stable_version_identity_hash(value: str) -> str:
    """Return the stable SHA-256 hash used for local and composed identities."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_model_local_identity_hash(*, query_sql: str, metadata_json: str) -> str:
    """Build a model's local identity hash from query SQL and non-query metadata."""

    return stable_version_identity_hash("\n".join((query_sql, metadata_json)))


def build_model_version_identity_hash(
    *,
    local_hash: str,
    upstream_deps: tuple[CompiledObjectKey, ...],
    upstream_version_hashes: dict[str, str],
    source_version_hashes: dict[str, str] | None = None,
) -> str:
    """Build a composed model version hash from local and upstream identities."""

    source_hashes: dict[str, str] = source_version_hashes or {}
    upstream_hashes: list[str] = []
    upstream_key: CompiledObjectKey
    for upstream_key in upstream_deps:
        if upstream_key.resource_type == CompiledResourceType.SOURCE:
            source_hash: str | None = source_hashes.get(upstream_key.name)
            if source_hash is not None:
                upstream_hashes.append(source_hash)
            continue
        if upstream_key.resource_type not in (
            CompiledResourceType.MODEL,
            CompiledResourceType.FUNCTION,
            CompiledResourceType.SEED,
        ):
            continue
        upstream_hash: str | None = upstream_version_hashes.get(upstream_key.name)
        if upstream_hash is not None:
            upstream_hashes.append(upstream_hash)
    return stable_version_identity_hash("\n".join((local_hash, *upstream_hashes)))
