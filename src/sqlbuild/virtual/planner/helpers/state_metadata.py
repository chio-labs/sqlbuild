"""Helpers for decoding virtual model-version metadata."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.shared.helpers.encoding import decode_state_text
from sqlbuild.virtual.state.models import ModelVersionRecord

_FUNCTION_STATE_VERSION_HASH: str = "current"


def decode_model_version_query_sqls(
    model_versions: dict[str, ModelVersionRecord | None],
) -> dict[str, str]:
    """Decode persisted model-version fingerprint SQL by model name."""

    result: dict[str, str] = {}
    for model_name, model_version in model_versions.items():
        if model_version is None:
            continue
        query_sql: str | None = decode_state_text(model_version.fingerprint_query_sql_b64)
        if query_sql is None:
            continue
        result[model_name] = query_sql
    return result


def decode_model_version_metadata_jsons(
    model_versions: dict[str, ModelVersionRecord | None],
) -> dict[str, str]:
    """Decode persisted model-version fingerprint metadata JSON by model name."""

    result: dict[str, str] = {}
    for model_name, model_version in model_versions.items():
        if model_version is None:
            continue
        metadata_json: str | None = decode_state_text(model_version.fingerprint_metadata_json_b64)
        if metadata_json is None:
            continue
        result[model_name] = metadata_json
    return result


def read_previous_function_query_sqls(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    graph: ProjectGraph,
) -> dict[str, str]:
    """Read persisted virtual function fingerprint SQL by function name."""

    function_versions: dict[str, ModelVersionRecord | None] = {
        function.name: backend.get_model_version(
            state_connection,
            schema=schema,
            model_name=function_state_name(function.name),
            version_hash=_FUNCTION_STATE_VERSION_HASH,
        )
        for function in graph.project.functions
    }
    return decode_model_version_query_sqls(function_versions)


def function_state_name(function_name: str) -> str:
    """Return the virtual state identity used for function fingerprints."""

    return f"__function__:{function_name}"
