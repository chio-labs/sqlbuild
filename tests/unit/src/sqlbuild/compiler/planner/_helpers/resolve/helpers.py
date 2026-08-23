"""Test helpers for resolve helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanContext


def build_cursor_intrinsic_model(*, config_values: dict[str, object]) -> CompiledModel:
    """Build a cursor incremental model that projects both cursor intrinsics."""

    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="events"),
        deps=(),
        name="events",
        relative_path=Path("models/events.sql"),
        query_sql="SELECT __cursor_start() AS batch_start, __cursor_end() AS batch_end",
        config=CompileModelConfig(values=config_values),
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name="events",
            qualified_name="main.events",
        ),
    )


def build_empty_model_plan_context() -> ModelPlanContext:
    """Build an empty model-resolution context."""

    return ModelPlanContext(
        model_locations={},
        models_by_name={},
        seed_locations={},
        function_locations={},
        source_map={},
        source_warehouse_columns={},
        star_exclude_keyword="EXCLUDE",
    )


def build_target(qualified: str | None, name: str) -> CompiledRelationLocation:
    """Build a minimal target for deferred tests."""

    return CompiledRelationLocation(database=None, schema=None, name=name, qualified_name=qualified)


class BracketUdfCallAdapter(DuckDbAdapter):
    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        arguments_sql: str = call_suffix_sql.removeprefix("(").removesuffix(")")
        return f"{target}[{arguments_sql}]"


class BracketTableFunctionCallAdapter(DuckDbAdapter):
    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
        arguments_sql: str = call_suffix_sql.removeprefix("(").removesuffix(")")
        return f"TABLE({target}[{arguments_sql}])"
