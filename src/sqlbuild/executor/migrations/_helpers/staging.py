"""Create and verify an isolated migration stage without touching the live destination."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, MigrationStagePlan, RelationInfo
from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.migrations.models import MigrationArtifactNames


def create_stage(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelMigrationPlanEntry,
    names: MigrationArtifactNames,
) -> MigrationTransfer:
    """Clone or copy the origin into the fresh stage, falling back to a copy if clone is refused."""

    plan: MigrationStagePlan = adapter.render_migration_stage(
        origin=entry.origin.qualified_name or entry.origin.name,
        stage=names.stage_qualified,
        origin_is_transient=entry.origin_is_transient,
        stage_is_transient=entry.stage_is_transient,
    )
    try:
        _execute_all(adapter=adapter, connection=connection, statements=plan.statements)
    except Exception as error:
        if (
            not plan.fallback_statements
            or plan.is_clone_refusal is None
            or not plan.is_clone_refusal(error)
        ):
            raise
        if _stage_exists(adapter=adapter, connection=connection, entry=entry, names=names):
            raise ExecutorInputError(
                f"migration clone into {names.stage_qualified} was refused but the stage now "
                "exists; refusing to adopt a stage of unknown completeness"
            ) from error
        logging.getLogger("sqlbuild.migrations").warning(
            "migration clone into '%s' was refused; copying instead: %s",
            names.stage_name,
            error,
        )
        _execute_all(adapter=adapter, connection=connection, statements=plan.fallback_statements)
        return MigrationTransfer.COPY
    return plan.transfer


def verify_stage(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelMigrationPlanEntry,
    names: MigrationArtifactNames,
    transfer: MigrationTransfer,
) -> None:
    """Refuse promotion unless the stage is complete, typed as planned, and matches the origin."""

    stage: RelationInfo = _listed(
        adapter=adapter,
        connection=connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=names.stage_name,
        missing=f"migration stage {names.stage_qualified} was not created",
    )
    origin: RelationInfo = _listed(
        adapter=adapter,
        connection=connection,
        database=entry.origin.database or entry.destination.database,
        schema=entry.origin.schema,
        name=entry.origin.name,
        missing=f"migration origin {entry.origin.qualified_name} no longer exists",
    )
    if (
        entry.stage_is_transient is not None
        and stage.is_transient is not None
        and stage.is_transient != entry.stage_is_transient
    ):
        raise ExecutorInputError(
            f"migration stage {names.stage_qualified} was not created with the destination's "
            "table type; refusing promotion"
        )
    columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(connection=connection, relations=(stage, origin))
    )
    if _column_names(columns.get(stage.identity, ())) != _column_names(
        columns.get(origin.identity, ())
    ):
        raise ExecutorInputError(
            f"migration stage {names.stage_qualified} columns differ from the origin; "
            "refusing promotion"
        )
    if transfer != MigrationTransfer.COPY:
        return
    stage_rows: int | None = _row_count(
        adapter=adapter, connection=connection, relation=names.stage_qualified
    )
    origin_rows: int | None = _row_count(
        adapter=adapter,
        connection=connection,
        relation=entry.origin.qualified_name or entry.origin.name,
    )
    if stage_rows != origin_rows:
        raise ExecutorInputError(
            f"migration stage {names.stage_qualified} holds {stage_rows} rows but the origin "
            f"holds {origin_rows}; refusing to promote an incomplete copy"
        )


def _stage_exists(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelMigrationPlanEntry,
    names: MigrationArtifactNames,
) -> bool:
    listed: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=entry.destination.database,
        schemas=(entry.destination.schema,) if entry.destination.schema is not None else None,
        names=(names.stage_name,),
    )
    return any(relation.name.lower() == names.stage_name.lower() for relation in listed)


def _execute_all(*, adapter: BaseAdapter, connection: Any, statements: tuple[str, ...]) -> None:
    statement: str
    for statement in statements:
        _ = adapter.execute(connection=connection, sql=statement)


def _listed(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str | None,
    name: str,
    missing: str,
) -> RelationInfo:
    listed: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=database,
        schemas=(schema,) if schema is not None else None,
        names=(name,),
    )
    relation: RelationInfo | None = next(
        (
            relation
            for relation in listed
            if relation.name.lower() == name.lower()
            and (relation.schema or "").lower() == (schema or "").lower()
        ),
        None,
    )
    if relation is None:
        raise ExecutorInputError(missing)
    return relation


def _column_names(columns: tuple[ColumnInfo, ...]) -> tuple[str, ...]:
    return tuple(column.name.lower() for column in columns)


def _row_count(*, adapter: BaseAdapter, connection: Any, relation: str) -> int | None:
    cursor: Any = adapter.execute(connection=connection, sql=f"SELECT COUNT(*) FROM {relation}")
    row: Any = cursor.fetchone()
    return None if row is None or row[0] is None else int(row[0])
