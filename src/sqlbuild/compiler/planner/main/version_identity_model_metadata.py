"""Build model metadata that participates in version identity."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.main.version_identity_metadata import (
    build_version_identity_metadata_json,
)


def build_model_version_identity_metadata_json(
    *,
    model: CompiledModel,
    function_local_hashes: dict[str, str] | None = None,
) -> str:
    """Build deterministic non-query model fingerprint metadata JSON."""

    function_hashes: dict[str, str] = function_local_hashes or {}
    local_function_hashes: dict[str, str] = {}
    upstream_key: Any
    for upstream_key in model.deps:
        if upstream_key.resource_type not in {
            CompiledResourceType.UDF,
            CompiledResourceType.TABLE_FN,
        }:
            continue
        upstream_hash: str | None = function_hashes.get(upstream_key.name)
        if upstream_hash is not None:
            local_function_hashes[upstream_key.name] = upstream_hash
    return build_version_identity_metadata_json(
        model_name=model.name,
        config_values=model.config.values,
        local_function_hashes=local_function_hashes,
        execution_signature=_model_execution_signature(model),
    )


def _model_execution_signature(model: CompiledModel) -> dict[str, object]:
    signature: dict[str, object] = {}
    contract_signature: dict[str, object] | None = _contract_output_signature(model)
    if contract_signature is not None:
        signature["contract"] = contract_signature
    if "config" in model.config.values:
        signature["custom_config"] = model.config.values["config"]
    if "placeholders" in model.config.values:
        signature["custom_placeholders"] = model.config.values["placeholders"]
    if "pre_hooks" in model.config.values:
        signature["pre_hooks"] = model.config.values["pre_hooks"]
    if "post_hooks" in model.config.values:
        signature["post_hooks"] = model.config.values["post_hooks"]
    return signature


def _contract_output_signature(model: CompiledModel) -> dict[str, object] | None:
    if model.config.values.get("contract") != "enforced":
        return None
    schema_entry: Any | None = model.schema_entry
    if schema_entry is None or not schema_entry.columns:
        return None
    return {
        "enforced": True,
        "columns": [
            {
                "name": column.name,
                "type": column.type,
                "nullable": column.nullable,
            }
            for column in schema_entry.columns
        ],
    }
