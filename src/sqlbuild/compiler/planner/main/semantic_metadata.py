"""Build semantic model metadata JSON for fingerprints."""

from __future__ import annotations

import json

from sqlbuild.compiler.planner.main.semantic_config import build_semantic_model_config


def build_semantic_model_metadata_json(
    *,
    model_name: str,
    config_values: dict[str, object],
    local_function_hashes: tuple[str, ...] = (),
) -> str:
    """Return deterministic metadata JSON for semantic model fingerprints."""

    return json.dumps(
        {
            "config": build_semantic_model_config(config_values),
            "local_function_hashes": list(local_function_hashes),
            "model_name": model_name,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
