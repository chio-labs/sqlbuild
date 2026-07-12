"""Public discovery constants."""

from __future__ import annotations

PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.toml"
LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.toml"
LEGACY_PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.yml"
LEGACY_LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.yml"
SCHEMA_FILE_NAME: str = "schema.yml"
SEED_FILE_SUFFIX: str = ".csv"
YAML_FILE_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})
RESERVED_MODEL_NAMES: frozenset[str] = frozenset({"_chain_"})
