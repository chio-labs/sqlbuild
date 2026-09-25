"""Model version identity hashing helpers."""

from __future__ import annotations

import hashlib

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import (
    NODE_TYPE_MODEL,
    NODE_TYPE_SEED,
    NODE_TYPE_TABLE_FN,
    NODE_TYPE_UDF,
)
from sqlbuild.compiler.planner.models import GraphNodeKey


def stable_version_identity_hash(value: str) -> str:
    """Return the stable SHA-256 hash used for local and composed identities."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_model_local_identity_hash(*, query_sql: str, metadata_json: str) -> str:
    """Build a model's local identity hash from query SQL and non-query metadata."""

    return stable_version_identity_hash("\n".join((query_sql, metadata_json)))


def graph_key_for_compiled_resource(
    *, resource_type: str | CompiledResourceType, name: str
) -> GraphNodeKey:
    normalized: CompiledResourceType | None = None
    if isinstance(resource_type, CompiledResourceType):
        normalized = resource_type
    else:
        try:
            normalized = CompiledResourceType(resource_type)
        except ValueError:
            normalized = None
    node_type: str = (
        resource_type.value if isinstance(resource_type, CompiledResourceType) else resource_type
    )
    if normalized == CompiledResourceType.MODEL:
        node_type = NODE_TYPE_MODEL
    elif normalized == CompiledResourceType.SEED:
        node_type = NODE_TYPE_SEED
    elif normalized == CompiledResourceType.UDF:
        node_type = NODE_TYPE_UDF
    elif normalized == CompiledResourceType.TABLE_FN:
        node_type = NODE_TYPE_TABLE_FN
    return GraphNodeKey(node_type=node_type, node_name=name)


def compose_native_graph_identity(
    *, local_hash: str, upstream_hashes: tuple[tuple[GraphNodeKey, str], ...]
) -> str:
    return stable_version_identity_hash(
        "\n".join((local_hash, *(upstream_hash for _, upstream_hash in upstream_hashes)))
    )
