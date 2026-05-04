"""Helpers for target validation unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_project(*, target: CompiledRelationTarget) -> CompiledProject:
    """Build a minimal compiled project for target validation tests."""

    return CompiledProject(
        run_id="run_123",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        models=(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL, name="stg_customers"
                ),
                deps=(),
                name="stg_customers",
                relative_path=Path("models/staging/stg_customers.sql"),
                query_sql="SELECT 1",
                config=CompileModelConfig(values={}),
                target=target,
            ),
        ),
    )
