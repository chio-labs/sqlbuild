"""Test helpers for pipeline helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_single_model_project(
    *,
    logical_schema: str | None,
    logical_database: str | None,
    physical_schema: str | None,
    physical_database: str | None,
) -> CompiledProject:
    """Build a project with one model for deferred target testing."""

    qualified: str | None = None
    if physical_schema is not None:
        qualified = f"{physical_schema}.test_model"

    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="test_model"),
        deps=(),
        name="test_model",
        relative_path=Path("models/test_model.sql"),
        query_sql="SELECT 1",
        config=CompileModelConfig(),
        target=CompiledRelationDestination(
            database=physical_database,
            schema=physical_schema,
            name="test_model",
            qualified_name=qualified,
            logical_schema=logical_schema,
            logical_database=logical_database,
        ),
    )
    return CompiledProject(
        run_id="test",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        models=(model,),
    )
