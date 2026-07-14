"""Build model metadata that participates in version identity."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.constants import (
    MODEL_CONTRACT_CONFIG_KEY,
    MODEL_CUSTOM_CONFIG_KEY,
    MODEL_PLACEHOLDERS_CONFIG_KEY,
    MODEL_POST_HOOKS_CONFIG_KEY,
    MODEL_PRE_HOOKS_CONFIG_KEY,
)
from sqlbuild.compiler.planner.main.planning.version_identity_metadata import (
    build_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.types import ContractPolicy


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
    if MODEL_CUSTOM_CONFIG_KEY in model.config.values:
        signature["custom_config"] = model.config.values[MODEL_CUSTOM_CONFIG_KEY]
    if MODEL_PLACEHOLDERS_CONFIG_KEY in model.config.values:
        signature["custom_placeholders"] = model.config.values[MODEL_PLACEHOLDERS_CONFIG_KEY]
    if MODEL_PRE_HOOKS_CONFIG_KEY in model.config.values:
        signature["pre_hooks"] = model.config.values[MODEL_PRE_HOOKS_CONFIG_KEY]
    if MODEL_POST_HOOKS_CONFIG_KEY in model.config.values:
        signature["post_hooks"] = model.config.values[MODEL_POST_HOOKS_CONFIG_KEY]
    return signature


def _contract_output_signature(model: CompiledModel) -> dict[str, object] | None:
    if model.config.values.get(MODEL_CONTRACT_CONFIG_KEY) != ContractPolicy.ENFORCED:
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
