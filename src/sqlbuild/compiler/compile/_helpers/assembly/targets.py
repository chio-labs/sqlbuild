"""Compiled model and seed relation target resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.compile.types import ModelInput


def build_model_relation_target(
    *, model_input: ModelInput, model_name: str
) -> CompiledRelationLocation:
    """Resolve one model's configured physical and logical destination."""

    raw_database: object | None = model_input.config.values.get("database")
    raw_schema: object | None = model_input.config.values.get("schema")
    raw_alias: object | None = model_input.config.values.get("alias")
    database: str | None = raw_database if isinstance(raw_database, str) else None
    schema: str | None = raw_schema if isinstance(raw_schema, str) else None
    name: str = raw_alias if isinstance(raw_alias, str) else model_name
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=name,
        qualified_name=None,
        logical_schema=model_input.config.logical_schema,
        logical_database=model_input.config.logical_database,
    )
