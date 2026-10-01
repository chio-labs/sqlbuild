"""Model version identity hashing helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from functools import partial

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import (
    NODE_TYPE_MODEL,
    NODE_TYPE_SEED,
    NODE_TYPE_TABLE_FN,
    NODE_TYPE_UDF,
)
from sqlbuild.compiler.fingerprints.exceptions import QueryFingerprintError
from sqlbuild.compiler.fingerprints.main.compute_function_definition_hash import (
    compute_function_definition_hash,
)
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.planner.constants import QUERY_FINGERPRINT_FAILED
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import GraphNodeKey

_FINGERPRINT_HELP: str = (
    "SQLBuild fingerprints the dialect token stream of compiled SQL to detect changes. "
    "Fix the SQL so the warehouse dialect tokenizer accepts it."
)


def stable_version_identity_hash(value: str) -> str:
    """Return the stable SHA-256 hash used for local and composed identities."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def model_definition_hash(*, model_name: str, query_sql: str, dialect: str | None) -> str:
    """Fingerprint a model query for change detection, naming the model when it cannot."""

    return _planner_fingerprint(
        subject=f"Model '{model_name}' SQL",
        compute=partial(compute_query_hash, query_sql=query_sql, dialect=dialect),
    )


def function_definition_hash(
    *, function_name: str, fingerprint_sql: str, language: str, dialect: str | None
) -> str:
    """Fingerprint a function definition for change detection, naming it when it cannot."""

    return _planner_fingerprint(
        subject=f"Function '{function_name}'",
        compute=partial(
            compute_function_definition_hash,
            fingerprint_sql=fingerprint_sql,
            language=language,
            dialect=dialect,
        ),
    )


def _planner_fingerprint(*, subject: str, compute: Callable[[], str]) -> str:
    try:
        return compute()
    except QueryFingerprintError as error:
        raise PlannerInputError(
            f"{subject} cannot be fingerprinted for change detection: {error}",
            code=QUERY_FINGERPRINT_FAILED,
            help=_FINGERPRINT_HELP,
        ) from None


def build_model_local_identity_hash(*, query_fingerprint: str, metadata_json: str) -> str:
    """Build a model's local identity hash from its query fingerprint and non-query metadata."""

    return stable_version_identity_hash("\n".join((query_fingerprint, metadata_json)))


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
