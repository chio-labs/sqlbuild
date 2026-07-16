"""Helpers for lineage helper tests."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sqlbuild.cli.commands.models import ColumnLineageTrace, LineageNode
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.compiler.lineage.types import ColumnLineageConfidence, ColumnTransformKind
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.spec.contracts.models import SchemaSeedEntry, SettingsConfig, SourceEntry


def build_lineage_test_graph() -> ProjectGraph:
    """Build a small static graph for lineage tests."""

    raw_orders_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    stg_orders_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "stg_orders")
    fact_orders_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "fact_orders"
    )
    daily_rollup_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "daily_rollup"
    )
    waffle_types_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.SEED, "waffle_types"
    )

    schema_file: DiscoveredSchemaFile = DiscoveredSchemaFile(
        file_path=Path("schema.yml"),
        relative_path=Path("schema.yml"),
        contents="",
        model_entries=(),
        seed_entries=(),
    )
    project: CompiledProject = CompiledProject(
        run_id="test-run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(
            _model(
                "stg_orders",
                stg_orders_key,
                (raw_orders_key,),
                "models/stg_orders.sql",
                query_sql="SELECT 1 AS order_id",
                inferred_columns=("order_id",),
            ),
            _model(
                "fact_orders",
                fact_orders_key,
                (stg_orders_key, waffle_types_key),
                "models/fact_orders.sql",
                query_sql='SELECT order_id FROM __ref("stg_orders")',
                inferred_columns=("order_id",),
            ),
            _model(
                "daily_rollup",
                daily_rollup_key,
                (fact_orders_key,),
                "models/daily_rollup.sql",
            ),
        ),
        sources=(
            CompiledSource(
                key=raw_orders_key,
                deps=(),
                name="raw_orders",
                source_entry=SourceEntry(name="raw_orders", table="raw_orders"),
                source_file=DiscoveredSourceFile(
                    file_path=Path("sources/raw.yml"),
                    relative_path=Path("sources/raw.yml"),
                    contents="",
                    source_entries=(),
                ),
            ),
        ),
        seeds=(
            CompiledSeed(
                key=waffle_types_key,
                deps=(),
                name="waffle_types",
                seed_file=DiscoveredSeedFile(
                    file_path=Path("seeds/waffle_types.csv"),
                    relative_path=Path("seeds/waffle_types.csv"),
                ),
                schema_entry=SchemaSeedEntry(name="waffle_types"),
                schema_file=schema_file,
                destination=_target("waffle_types"),
            ),
        ),
    )
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        raw_orders_key: (),
        waffle_types_key: (),
        stg_orders_key: (raw_orders_key,),
        fact_orders_key: (stg_orders_key, waffle_types_key),
        daily_rollup_key: (fact_orders_key,),
    }
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        raw_orders_key: (stg_orders_key,),
        waffle_types_key: (fact_orders_key,),
        stg_orders_key: (fact_orders_key,),
        fact_orders_key: (daily_rollup_key,),
        daily_rollup_key: (),
    }
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index={"marts": frozenset({fact_orders_key, daily_rollup_key})},
        path_index={
            stg_orders_key: "staging",
            fact_orders_key: "marts",
            daily_rollup_key: "marts",
        },
        all_keys={
            "raw_orders": raw_orders_key,
            "waffle_types": waffle_types_key,
            "stg_orders": stg_orders_key,
            "fact_orders": fact_orders_key,
            "daily_rollup": daily_rollup_key,
        },
    )


def node_ids(graph_nodes: Iterable[LineageNode]) -> tuple[str, ...]:
    return tuple(f"{node.key.resource_type}:{node.key.name}" for node in graph_nodes)


def edge_ids(
    graph_edges: Iterable[tuple[CompiledObjectKey, CompiledObjectKey]],
) -> tuple[str, ...]:
    return tuple(
        f"{parent.resource_type}:{parent.name}->{child.resource_type}:{child.name}"
        for parent, child in graph_edges
    )


def build_column_lineage_trace() -> ColumnLineageTrace:
    target: QualifiedLineageColumn = QualifiedLineageColumn(
        resource_type=CompiledResourceType.MODEL,
        resource_name="fact_orders",
        column_name="line_total_cents",
    )
    return ColumnLineageTrace(
        target=target,
        direction="upstream",
        max_depth=3,
        analyzed_model_count=7,
        truncated=True,
        trace=(
            ColumnLineageEdge(
                source=QualifiedLineageColumn(
                    resource_type=CompiledResourceType.MODEL,
                    resource_name="stg_orders",
                    column_name="quantity",
                ),
                target=target,
                transform_kind=ColumnTransformKind.EXPRESSION,
                confidence=ColumnLineageConfidence.HIGH,
            ),
            ColumnLineageEdge(
                source=QualifiedLineageColumn(
                    resource_type=CompiledResourceType.MODEL,
                    resource_name="wide_model_1",
                    column_name="line_total_cents",
                ),
                target=target,
                transform_kind=ColumnTransformKind.STAR,
                confidence=ColumnLineageConfidence.MEDIUM,
            ),
        ),
    )


def build_large_column_lineage_trace() -> ColumnLineageTrace:
    target: QualifiedLineageColumn = QualifiedLineageColumn(
        resource_type=CompiledResourceType.MODEL,
        resource_name="fact_orders",
        column_name="order_id",
    )
    return ColumnLineageTrace(
        target=target,
        direction="downstream",
        trace=tuple(
            ColumnLineageEdge(
                source=target,
                target=QualifiedLineageColumn(
                    resource_type=CompiledResourceType.MODEL,
                    resource_name=f"consumer_{index:02d}",
                    column_name="order_id",
                ),
                transform_kind=ColumnTransformKind.DIRECT,
                confidence=ColumnLineageConfidence.HIGH,
            )
            for index in range(30)
        ),
    )


def _model(
    name: str,
    key: CompiledObjectKey,
    deps: tuple[CompiledObjectKey, ...],
    relative_path: str,
    query_sql: str = "SELECT 1",
    inferred_columns: tuple[str, ...] = (),
) -> CompiledModel:
    return CompiledModel(
        key=key,
        deps=deps,
        name=name,
        relative_path=Path(relative_path),
        query_sql=query_sql,
        config=CompileModelConfig(),
        destination=_target(name),
        inferred_columns=tuple(InferredColumn(column) for column in inferred_columns),
    )


def _target(name: str) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=None,
        schema="main",
        name=name,
        qualified_name=f"main.{name}",
    )
