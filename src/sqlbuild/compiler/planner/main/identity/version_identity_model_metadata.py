"""Build model metadata that participates in version identity."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.constants import SQL_HOOK_IDENTITY_FIELDS
from sqlbuild.compiler.discovery.main.serialize_hook_entries import serialize_hook_entries
from sqlbuild.compiler.planner._helpers.identity.model_metadata import contract_output_signature
from sqlbuild.compiler.planner.constants import (
    MODEL_CUSTOM_CONFIG_KEY,
    MODEL_PLACEHOLDERS_CONFIG_KEY,
    MODEL_POST_HOOKS_CONFIG_KEY,
    MODEL_PRE_HOOKS_CONFIG_KEY,
)
from sqlbuild.compiler.planner.main.identity._version_identity_metadata import (
    build_version_identity_metadata_json,
)


def build_model_version_identity_metadata_json(
    *,
    model: CompiledModel,
    function_local_hashes: dict[str, str] | None = None,
    hook_version_hashes: dict[str, str] | None = None,
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
        execution_signature=_model_execution_signature(
            model=model,
            hook_version_hashes=hook_version_hashes or {},
        ),
    )


def _model_execution_signature(
    *, model: CompiledModel, hook_version_hashes: dict[str, str]
) -> dict[str, object]:
    signature: dict[str, object] = {}
    contract_signature: dict[str, object] | None = contract_output_signature(model=model)
    if contract_signature is not None:
        signature["contract"] = contract_signature
    if MODEL_CUSTOM_CONFIG_KEY in model.config.values:
        signature["custom_config"] = model.config.values[MODEL_CUSTOM_CONFIG_KEY]
    if MODEL_PLACEHOLDERS_CONFIG_KEY in model.config.values:
        signature["custom_placeholders"] = model.config.values[MODEL_PLACEHOLDERS_CONFIG_KEY]
    if MODEL_PRE_HOOKS_CONFIG_KEY in model.config.values:
        signature["pre_hooks"] = _hook_execution_signature(
            value=model.config.values[MODEL_PRE_HOOKS_CONFIG_KEY],
            hook_version_hashes=hook_version_hashes,
        )
    if MODEL_POST_HOOKS_CONFIG_KEY in model.config.values:
        signature["post_hooks"] = _hook_execution_signature(
            value=model.config.values[MODEL_POST_HOOKS_CONFIG_KEY],
            hook_version_hashes=hook_version_hashes,
        )
    return signature


def _hook_execution_signature(
    *, value: object, hook_version_hashes: dict[str, str]
) -> list[dict[str, object]]:
    return serialize_hook_entries(
        value=value,
        sql_fields=SQL_HOOK_IDENTITY_FIELDS,
        python_hook_fields={
            hook_name: {"version_hash": version_hash}
            for hook_name, version_hash in hook_version_hashes.items()
        },
    )
