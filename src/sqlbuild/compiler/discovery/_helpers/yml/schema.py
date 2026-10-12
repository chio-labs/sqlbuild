"""Parsing of authored schema.yml files, run natively."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.yml.yaml_classes import yaml_entry_classes
from sqlbuild.spec.contracts.models import SchemaModelEntry, SchemaSeedEntry


def parse_loaded_schema_yml(
    *, loaded: object, file_path: Path
) -> tuple[tuple[SchemaModelEntry, ...], tuple[SchemaSeedEntry, ...]]:
    """Parse the document one schema.yml file loads to into raw model and seed metadata."""

    return (), _native.parse_schema_document(loaded, str(file_path), yaml_entry_classes())
