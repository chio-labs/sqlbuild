"""Shared cross-cutting constants."""

from __future__ import annotations

LOGGER_ROOT_NAME: str = "sqlbuild"
SCENARIO_ARTIFACT_PREFIX: str = "__sqb_"
SCENARIO_HASH_PREFIX_LENGTH: int = 12
SCENARIO_SHORTENED_LOGICAL_HASH_LENGTH: int = 8
SCENARIO_ARTIFACT_KINDS: tuple[str, ...] = ("source", "ref", "seed", "model")
