"""Helpers for lineage helper tests."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.lineage.models import LineageNode
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.spec.models.project import SettingsConfig
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


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
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(
            _model("stg_orders", stg_orders_key, (raw_orders_key,), "models/stg_orders.sql"),
            _model(
                "fact_orders",
                fact_orders_key,
                (stg_orders_key, waffle_types_key),
                "models/fact_orders.sql",
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
                target=_target("waffle_types"),
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


def _model(
    name: str,
    key: CompiledObjectKey,
    deps: tuple[CompiledObjectKey, ...],
    relative_path: str,
) -> CompiledModel:
    return CompiledModel(
        key=key,
        deps=deps,
        name=name,
        relative_path=Path(relative_path),
        query_sql="SELECT 1",
        config=CompileModelConfig(),
        target=_target(name),
    )


def _target(name: str) -> CompiledRelationTarget:
    return CompiledRelationTarget(
        database=None,
        schema="main",
        name=name,
        qualified_name=f"main.{name}",
    )
