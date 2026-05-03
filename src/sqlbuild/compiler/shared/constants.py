"""Shared compiler filesystem conventions."""

from __future__ import annotations

SCHEMA_FILE_NAME: str = "schema.yml"
SEED_FILE_SUFFIX: str = ".csv"
YAML_FILE_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})
