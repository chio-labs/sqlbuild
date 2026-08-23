"""Kata evaluation test helpers."""

from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_project(
    *,
    name: str,
    relative_path: str,
    sql: str,
    config_values: dict[str, object],
    references: tuple[CompileSqlReference, ...] = (),
) -> CompiledProject:
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        deps=(),
        name=name,
        relative_path=Path(relative_path),
        query_sql=sql,
        authored_sql=sql,
        config=CompileModelConfig(values=config_values),
        references=references,
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=name,
        ),
    )
    return CompiledProject(
        run_id="test",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=(model,),
    )
