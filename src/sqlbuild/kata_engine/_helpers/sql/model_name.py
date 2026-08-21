"""SQLBuild model-name grammar parsing."""

from __future__ import annotations

import re

from sqlbuild.kata_engine.constants import MAX_ENTITY_PARTS, MODEL_NAME_PART_COUNT
from sqlbuild.kata_engine.models import ModelNameParts

_LAYERS: tuple[str, ...] = (
    "int_enriched",
    "int_clean",
    "stg_v",
    "mart_v",
    "int_v",
    "stg",
    "mart",
)
_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_model_name(name: str) -> ModelNameParts | None:
    """Parse the closed kata model-name grammar."""

    parts: list[str] = name.split("__")
    if len(parts) < MODEL_NAME_PART_COUNT or not _TOKEN_PATTERN.fullmatch(parts[0]):
        return None
    domain: str = parts[0]
    tail: str = "__".join(parts[1:])
    for layer in _LAYERS:
        prefix: str = f"{layer}__"
        if tail.startswith(prefix):
            entity_parts: list[str] = tail[len(prefix) :].split("__")
            if len(entity_parts) > MAX_ENTITY_PARTS or any(
                not _TOKEN_PATTERN.fullmatch(part) for part in entity_parts
            ):
                return None
            return ModelNameParts(
                domain=domain,
                layer=layer,
                entity=entity_parts[0],
                source=entity_parts[1] if len(entity_parts) > 1 else None,
                is_view=layer.endswith("_v"),
            )
    return None


def apparent_layer(name: str) -> str | None:
    """Return the raw layer-looking token for invalid-name diagnostics."""

    parts: list[str] = name.split("__", maxsplit=2)
    return parts[1] if len(parts) == MODEL_NAME_PART_COUNT else None
