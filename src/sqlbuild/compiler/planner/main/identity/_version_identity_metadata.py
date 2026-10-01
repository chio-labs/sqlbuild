"""Build non-query metadata that participates in model version identity."""

from __future__ import annotations

import json

from sqlbuild.compiler.planner.constants import LOCAL_FUNCTION_HASHES_METADATA_KEY
from sqlbuild.compiler.planner.main.identity._version_identity_config import (
    build_version_identity_config,
)


def build_version_identity_metadata_json(
    *,
    model_name: str,
    config_values: dict[str, object],
    local_function_hashes: dict[str, str] | None = None,
    execution_signature: dict[str, object] | None = None,
) -> str:
    """Return deterministic metadata JSON for model version identity."""

    return json.dumps(
        {
            "config": build_version_identity_config(config_values),
            "execution_signature": execution_signature or {},
            LOCAL_FUNCTION_HASHES_METADATA_KEY: local_function_hashes or {},
            "model_name": model_name,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
