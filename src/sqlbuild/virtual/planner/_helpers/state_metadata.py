"""Helpers for decoding virtual model-version metadata."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.state.main.encoding._decode_state_text import decode_state_text
from sqlbuild.virtual.state.models import FunctionVersionRecord, ModelVersionRecord


def decode_model_version_query_sqls(
    model_versions: dict[str, ModelVersionRecord | None],
) -> dict[str, str]:
    """Decode persisted model-version fingerprint SQL by model name."""

    result: dict[str, str] = {}
    for model_name, model_version in model_versions.items():
        if model_version is None:
            continue
        query_sql: str | None = decode_state_text(model_version.definition_text_b64)
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
        metadata_json: str | None = decode_state_text(model_version.identity_metadata_json_b64)
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
    virtual_environment_name: str,
) -> dict[str, str]:
    """Read persisted virtual function fingerprint SQL by function name."""

    function_refs: dict[str, str] = {
        ref.function_name: ref.version_hash
        for ref in backend.get_virtual_environment_function_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
        )
    }
    function_versions: dict[str, FunctionVersionRecord | None] = {
        function.name: backend.get_function_version(
            connection=state_connection,
            schema=schema,
            function_name=function.name,
            version_hash=function_refs[function.name],
        )
        for function in graph.project.functions
        if function.name in function_refs
    }
    result: dict[str, str] = {}
    for function_name, function_version in function_versions.items():
        if function_version is None:
            continue
        query_sql: str | None = decode_state_text(function_version.definition_text_b64)
        if query_sql is not None:
            result[function_name] = query_sql
    return result
