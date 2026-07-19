"""Virtual physical-version seeding helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalStrategy, PlanAction
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.virtual.state.models import PhysicalRelationAncestryRecord, PhysicalRelationRecord
from sqlbuild.virtual.state.types import PhysicalArtifactType


def read_seed_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    seed_version_hashes: dict[str, str],
) -> dict[str, PhysicalRelationRecord]:
    """Read available physical relations for seed version hashes."""

    relations: dict[str, PhysicalRelationRecord] = {}
    seed_name: str
    version_hash: str
    for seed_name, version_hash in seed_version_hashes.items():
        relation: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
            connection=state_connection,
            schema=schema,
            artifact_type=PhysicalArtifactType.SEED,
            artifact_name=seed_name,
            version_hash=version_hash,
        )
        if relation is not None:
            relations[seed_name] = relation
    return relations


def seed_virtual_physical_version(
    *,
    adapter: BaseAdapter,
    connection: Any,
    backend: Any,
    state_connection: Any,
    state_schema: str,
    entry: ModelPlanEntry,
    parent_relation: PhysicalRelationRecord | None,
    version_hash: str | None,
) -> None:
    """Seed one incremental physical version target before DML execution."""

    recorder: StatementRecorder = StatementRecorder()
    if not _should_seed_physical_version(entry=entry):
        return
    if parent_relation is None or version_hash is None:
        return
    if parent_relation.version_hash == version_hash:
        return

    adapter.ensure_schema(
        connection=connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        statement_recorder=recorder,
    )
    target: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    if adapter.relation_exists(
        connection=connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    ):
        adapter.drop(
            connection=connection,
            destination=target,
            if_exists=True,
            statement_recorder=recorder,
        )
    source: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=parent_relation.database_name,
        schema=parent_relation.schema_name,
        name=parent_relation.relation_name,
    )
    seed_strategy: str = _seed_physical_relation(
        adapter=adapter,
        connection=connection,
        origin=source,
        destination=target,
        entry=entry,
        origin_is_transient=_origin_is_transient(
            adapter=adapter,
            connection=connection,
            database=parent_relation.database_name,
            schema=parent_relation.schema_name,
            name=parent_relation.relation_name,
        ),
        statement_recorder=recorder,
    )
    backend.upsert_physical_relation_ancestry(
        connection=state_connection,
        schema=state_schema,
        record=PhysicalRelationAncestryRecord(
            model_name=entry.name,
            version_hash=version_hash,
            parent_model_name=parent_relation.artifact_name,
            parent_version_hash=parent_relation.version_hash,
            seed_strategy=seed_strategy,
        ),
    )


def _seed_physical_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin: str,
    destination: str,
    entry: ModelPlanEntry,
    origin_is_transient: bool,
    statement_recorder: StatementRecorder,
) -> str:
    if _requires_append_bounded_seed(entry=entry):
        cursor_start: str = _cursor_start_for_append_seed(entry=entry)
        adapter.create_table_as(
            connection=connection,
            destination=destination,
            sql=adapter.render_seed_select_before_cursor(
                origin=origin,
                cursor_column=entry.cursor_column or "",
                cursor_end_exclusive=cursor_start,
                cursor_type=entry.cursor_type,
            ),
            statement_recorder=statement_recorder,
        )
        return "bounded_append_copy"

    if adapter.supports_durable_clone():
        adapter.durable_clone(
            connection=connection,
            origin=origin,
            destination=destination,
            origin_is_transient=origin_is_transient,
            statement_recorder=statement_recorder,
        )
        return "durable_clone"

    adapter.create_table_as(
        connection=connection,
        destination=destination,
        sql=f"SELECT * FROM {origin}",
        statement_recorder=statement_recorder,
    )
    return "copy"


def _origin_is_transient(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
    name: str,
) -> bool:
    """Return whether the origin warehouse relation is transient, defaulting to False."""

    if schema is None:
        return False
    relations: tuple[Any, ...] = adapter.list_relations(
        connection=connection, database=database, schemas=(schema,), names=(name,)
    )
    target_name: str = name.lower()
    for relation in relations:
        if relation.name == target_name:
            return bool(relation.is_transient)
    return False


def _should_seed_physical_version(*, entry: ModelPlanEntry) -> bool:
    return entry.action in INCREMENTAL_ACTIONS or entry.action == PlanAction.CUSTOM


def _requires_append_bounded_seed(*, entry: ModelPlanEntry) -> bool:
    return (
        entry.incremental_strategy == IncrementalStrategy.APPEND and entry.cursor_bounds is not None
    )


def _cursor_start_for_append_seed(*, entry: ModelPlanEntry) -> str:
    if entry.cursor_column is None or entry.cursor_bounds is None:
        raise PlannerInputError(
            f"bounded append seeding for '{entry.name}' requires cursor bounds and cursor_column"
        )
    return entry.cursor_bounds.start


def resolve_virtual_seed_selection(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve the seed names matched by the requested selectors."""

    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    return tuple(
        sorted(key.name for key in selected_keys if key.resource_type == CompiledResourceType.SEED)
    )


def include_stale_upstream_seed_names(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    selected_seed_names: tuple[str, ...],
    stale_seed_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Add stale seeds feeding the selected models to the selected seed names."""

    selected: set[str] = set(selected_seed_names)
    stale_seed_name_set: frozenset[str] = frozenset(stale_seed_names)
    pending: list[CompiledObjectKey] = [
        model.key for model in graph.project.models if model.name in selected_model_names
    ]
    seen: set[CompiledObjectKey] = set()
    while pending:
        key: CompiledObjectKey = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        upstream_key: CompiledObjectKey
        for upstream_key in graph.upstream_deps.get(key, ()):
            if upstream_key.resource_type == CompiledResourceType.SEED:
                if upstream_key.name in stale_seed_name_set:
                    selected.add(upstream_key.name)
                continue
            pending.append(upstream_key)
    return tuple(sorted(selected))
