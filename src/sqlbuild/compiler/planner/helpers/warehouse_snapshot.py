"""Gather a frozen point-in-time warehouse snapshot for planning."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompiledSeed
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.models import WarehouseSnapshot


def gather_warehouse_snapshot(
    *,
    project: CompiledProject,
    adapter: Any,
    connection: Any,
    execute: Any,
) -> WarehouseSnapshot:
    """Gather relations, columns, and fingerprints for all target schemas."""

    database: str | None = _resolve_database(project)
    schemas: tuple[str, ...] = _collect_target_schemas(project)
    if not schemas:
        return WarehouseSnapshot()

    relations: dict[str, RelationInfo] = _gather_relations(
        adapter=adapter, connection=connection, database=database, schemas=schemas
    )
    columns: dict[str, tuple[ColumnInfo, ...]] = _gather_columns(
        adapter=adapter, connection=connection, database=database, schemas=schemas
    )
    fingerprints: dict[str, Fingerprint] = _gather_fingerprints(
        connection=connection, execute=execute, database=database, schemas=schemas
    )
    return WarehouseSnapshot(
        existing_relations=relations,
        existing_columns=columns,
        fingerprints=fingerprints,
    )


def _resolve_database(project: CompiledProject) -> str | None:
    """Extract the database from the first model target that declares one."""

    model: CompiledModel
    for model in project.models:
        if model.target.database is not None:
            return model.target.database
    seed: CompiledSeed
    for seed in project.seeds:
        if seed.target.database is not None:
            return seed.target.database
    return None


def _collect_target_schemas(project: CompiledProject) -> tuple[str, ...]:
    """Collect distinct non-null target schemas from models and seeds."""

    schemas: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if model.target.schema is not None:
            schemas.add(model.target.schema)
    seed: CompiledSeed
    for seed in project.seeds:
        if seed.target.schema is not None:
            schemas.add(seed.target.schema)
    return tuple(sorted(schemas))


def _gather_relations(
    *,
    adapter: Any,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, RelationInfo]:
    """Fetch all existing relations across target schemas."""

    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection, database=database, schemas=schemas
    )
    result: dict[str, RelationInfo] = {}
    relation: RelationInfo
    for relation in relations:
        if relation.name == FINGERPRINT_TABLE_NAME:
            continue
        result[relation.name] = relation
    return result


def _gather_columns(
    *,
    adapter: Any,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Fetch column metadata for all relations across target schemas."""

    all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection, database=database, schemas=schemas
    )
    return {name: cols for name, cols in all_columns.items() if name != FINGERPRINT_TABLE_NAME}


def _gather_fingerprints(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, Fingerprint]:
    """Read latest fingerprints across all target schemas."""

    merged: dict[str, Fingerprint] = {}
    schema: str
    for schema in schemas:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection, execute=execute, database=database, schema=schema
        )
        merged.update(fingerprint_set.fingerprints)
    return merged
