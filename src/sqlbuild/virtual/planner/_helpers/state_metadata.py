"""Helpers for decoding virtual model-version metadata."""

from __future__ import annotations

from sqlbuild.virtual.state.main.encoding._decode_state_text import decode_state_text
from sqlbuild.virtual.state.models import ModelVersionRecord


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
