"""Read-only warehouse evidence gathered once for all model migrations in one plan."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.relations.main.get_columns_for_inspection import get_columns_for_inspection
from sqlbuild.adapter.relations.main.list_relations_for_inspection import (
    list_relations_for_inspection,
)
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME, NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.migrations.constants import (
    COLUMN_MIGRATION_TABLE_NAME,
    MIGRATION_TABLE_NAME,
    OLD_NAME_VIEW_TABLE_NAME,
)
from sqlbuild.compiler.migrations.main._project_old_name_views import project_old_name_views
from sqlbuild.compiler.migrations.main._read_column_events import read_column_migration_events
from sqlbuild.compiler.migrations.main._read_events import read_migration_events
from sqlbuild.compiler.migrations.main.read_old_name_view_events import (
    read_old_name_view_events,
)
from sqlbuild.compiler.migrations.main.stored_old_name_view_columns import (
    stored_old_name_view_columns,
)
from sqlbuild.compiler.migrations.models import (
    ColumnMigrationEvent,
    MigrationEvent,
    MigrationRelation,
    OldNameViewEvent,
    OldNameViewHistory,
)
from sqlbuild.compiler.planner.models import WarehouseFingerprints


class MigrationStateInspection:
    """Relations, fingerprints, and migration events for one planning database."""

    def __init__(
        self,
        *,
        adapter: BaseAdapter,
        connection: Any,
        database: str | None,
        known_fingerprints: WarehouseFingerprints | None = None,
    ) -> None:
        self._adapter: BaseAdapter = adapter
        self._connection: Any = connection
        self._database: str | None = database
        self._known_fingerprints: dict[str, tuple[Fingerprint, ...]] = (
            known_fingerprints.unfiltered_schemas
            if known_fingerprints is not None and known_fingerprints.unfiltered_database == database
            else {}
        )
        self._read_schemas: set[str] = set()
        self._fingerprints: dict[str, tuple[Fingerprint, ...]] = {}
        self._events: list[MigrationEvent] = []
        self._event_schemas: set[str] = set()
        self._relations: dict[tuple[str, str], RelationInfo] = {}
        self._columns: dict[tuple[str, str], tuple[ColumnInfo, ...]] = {}
        self._column_event_schemas: set[str] = set()
        self._column_events: list[ColumnMigrationEvent] = []
        self._old_name_schemas: set[str] = set()
        self._old_name_moves: list[MigrationEvent] = []
        self._old_name_facts: list[OldNameViewEvent] = []

    @property
    def database(self) -> str | None:
        """Return the database whose namespaces this inspection reads."""

        return self._database

    @property
    def events(self) -> tuple[MigrationEvent, ...]:
        """Return every migration event read so far."""

        return tuple(self._events)

    @property
    def column_events(self) -> tuple[ColumnMigrationEvent, ...]:
        """Return every column migration event read so far."""

        return tuple(self._column_events)

    def inspect_column_events(self, *, schemas: set[str]) -> None:
        """Read the column migration state table once for every schema not inspected yet."""

        pending: tuple[str, ...] = tuple(
            sorted(schema for schema in schemas if schema.lower() not in self._column_event_schemas)
        )
        if not pending:
            return
        self._column_event_schemas.update(schema.lower() for schema in pending)
        listed: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=self._adapter,
            connection=self._connection,
            database=self._database,
            schemas=pending,
            names=(COLUMN_MIGRATION_TABLE_NAME,),
        )
        present: set[str] = {
            (relation.schema or "").lower()
            for relation in listed
            if relation.name.lower() == COLUMN_MIGRATION_TABLE_NAME
        }
        schema: str
        for schema in pending:
            if schema.lower() in present:
                self._column_events.extend(
                    read_column_migration_events(
                        connection=self._connection,
                        execute=self._adapter.execute,
                        database=self._database,
                        schema=schema,
                        render_qualified_name=self._adapter.render_qualified_name,
                    )
                )

    @property
    def old_name_histories(self) -> tuple[OldNameViewHistory, ...]:
        """Return the old-name history of every move read by ``inspect_old_name_views``."""

        return project_old_name_views(moves=self._old_name_moves, facts=self._old_name_facts)

    def inspect_old_name_views(self, *, schemas: set[str]) -> None:
        """Read moves and old-name facts once for every schema not inspected yet."""

        pending: tuple[str, ...] = tuple(
            sorted(schema for schema in schemas if schema.lower() not in self._old_name_schemas)
        )
        if not pending:
            return
        self._old_name_schemas.update(schema.lower() for schema in pending)
        listed: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=self._adapter,
            connection=self._connection,
            database=self._database,
            schemas=pending,
            names=(MIGRATION_TABLE_NAME, OLD_NAME_VIEW_TABLE_NAME),
        )
        state_tables: set[tuple[str, str]] = {
            ((relation.schema or "").lower(), relation.name.lower()) for relation in listed
        }
        schema: str
        for schema in pending:
            if (schema.lower(), OLD_NAME_VIEW_TABLE_NAME) not in state_tables or (
                schema.lower(),
                MIGRATION_TABLE_NAME,
            ) not in state_tables:
                continue
            self._old_name_facts.extend(
                read_old_name_view_events(
                    connection=self._connection,
                    execute=self._adapter.execute,
                    database=self._database,
                    schema=schema,
                    stored_columns=stored_old_name_view_columns(
                        adapter=self._adapter,
                        connection=self._connection,
                        database=self._database,
                        schema=schema,
                    ),
                    render_qualified_name=self._adapter.render_qualified_name,
                )
            )
            self._old_name_moves.extend(
                read_migration_events(
                    connection=self._connection,
                    execute=self._adapter.execute,
                    database=self._database,
                    schema=schema,
                    render_qualified_name=self._adapter.render_qualified_name,
                )
            )

    def inspect_migration_events(self, *, schemas: set[str]) -> None:
        """Read migration events once from schemas known to hold the migration table."""

        schema: str
        for schema in sorted(schemas):
            if schema.lower() in self._event_schemas:
                continue
            self._event_schemas.add(schema.lower())
            self._events.extend(
                read_migration_events(
                    connection=self._connection,
                    execute=self._adapter.execute,
                    database=self._database,
                    schema=schema,
                    render_qualified_name=self._adapter.render_qualified_name,
                )
            )

    def inspect_schemas(self, *, schemas: set[str]) -> None:
        """Read state tables once for every schema not inspected yet."""

        pending: tuple[str, ...] = tuple(
            sorted(schema for schema in schemas if schema.lower() not in self._read_schemas)
        )
        if not pending:
            return
        self._read_schemas.update(schema.lower() for schema in pending)
        listed: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=self._adapter,
            connection=self._connection,
            database=self._database,
            schemas=pending,
            names=(MIGRATION_TABLE_NAME, FINGERPRINT_TABLE_NAME),
        )
        state_tables: set[tuple[str, str]] = {
            ((relation.schema or "").lower(), relation.name.lower()) for relation in listed
        }
        schema: str
        for schema in pending:
            if (schema.lower(), MIGRATION_TABLE_NAME) in state_tables:
                self.inspect_migration_events(schemas={schema})
            if (schema.lower(), FINGERPRINT_TABLE_NAME) in state_tables:
                self._fingerprints[schema.lower()] = self._read_model_fingerprints(schema=schema)

    def _read_model_fingerprints(self, *, schema: str) -> tuple[Fingerprint, ...]:
        latest: tuple[Fingerprint, ...] | None = self._known_fingerprints.get(schema.lower())
        if latest is None:
            fingerprint_set: FingerprintSet = read_latest_fingerprints(
                connection=self._connection,
                execute=self._adapter.execute,
                table_exists=True,
                database=self._database,
                schema=schema,
                render_qualified_name=self._adapter.render_qualified_name,
                render_read_latest_sql=self._adapter.render_read_latest_fingerprints_sql,
            )
            latest = tuple((fingerprint_set.fingerprints_by_identity or {}).values())
        return tuple(
            fingerprint for fingerprint in latest if fingerprint.node_type == NODE_TYPE_MODEL
        )

    def inspect_relations(self, *, locations: tuple[CompiledRelationLocation, ...]) -> None:
        """List candidate relations and their columns with one metadata read."""

        pending: tuple[CompiledRelationLocation, ...] = tuple(
            location
            for location in locations
            if location.schema is not None and _relation_key(location) not in self._relations
        )
        if not pending:
            return
        listed: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=self._adapter,
            connection=self._connection,
            database=self._database,
            schemas=tuple(sorted({location.schema or "" for location in pending})),
            names=tuple(sorted({location.name for location in pending})),
        )
        wanted: set[tuple[str, str]] = {_relation_key(location) for location in pending}
        matched: tuple[RelationInfo, ...] = tuple(
            relation for relation in listed if _listed_key(relation) in wanted
        )
        columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
            get_columns_for_inspection(
                adapter=self._adapter, connection=self._connection, relations=matched
            )
            if matched
            else {}
        )
        relation: RelationInfo
        for relation in matched:
            self._relations[_listed_key(relation)] = relation
            self._columns[_listed_key(relation)] = columns.get(relation.identity, ())

    def relation(self, location: CompiledRelationLocation) -> RelationInfo | None:
        """Return the listed relation for a location."""

        return self._relations.get(_relation_key(location))

    def relation_columns(self, location: CompiledRelationLocation) -> tuple[ColumnInfo, ...]:
        """Return listed columns for a location."""

        return self._columns.get(_relation_key(location), ())

    def model_fingerprint(
        self, *, location: CompiledRelationLocation, model_name: str | None
    ) -> Fingerprint | None:
        """Return the latest model fingerprint that built the location or named model."""

        candidates: tuple[Fingerprint, ...] = self._fingerprints.get(
            (location.schema or "").lower(), ()
        )
        target: MigrationRelation = MigrationRelation(
            database=location.database, schema=location.schema, name=location.name
        )
        by_relation: tuple[Fingerprint, ...] = tuple(
            fingerprint
            for fingerprint in candidates
            if _fingerprint_built(fingerprint=fingerprint, target=target)
        )
        if by_relation:
            return max(by_relation, key=_fingerprint_order)
        if model_name is None:
            return None
        named: tuple[Fingerprint, ...] = tuple(
            fingerprint for fingerprint in candidates if fingerprint.node_name == model_name
        )
        return max(named, key=_fingerprint_order) if named else None

    def named_fingerprint(self, *, model_name: str) -> Fingerprint | None:
        """Return the newest model fingerprint with this node name in any inspected schema."""

        matches: list[Fingerprint] = []
        fingerprints: tuple[Fingerprint, ...]
        for fingerprints in self._fingerprints.values():
            matches.extend(
                fingerprint for fingerprint in fingerprints if fingerprint.node_name == model_name
            )
        return max(matches, key=_fingerprint_order) if matches else None

    def orphan_fingerprints(
        self, *, project_model_names: frozenset[str]
    ) -> tuple[Fingerprint, ...]:
        """Return latest model fingerprints whose names are no longer in the project."""

        orphans: list[Fingerprint] = []
        fingerprints: tuple[Fingerprint, ...]
        for fingerprints in self._fingerprints.values():
            orphans.extend(
                fingerprint
                for fingerprint in fingerprints
                if fingerprint.node_name not in project_model_names
            )
        return tuple(orphans)


def _relation_key(location: CompiledRelationLocation) -> tuple[str, str]:
    return ((location.schema or "").lower(), location.name.lower())


def _listed_key(relation: RelationInfo) -> tuple[str, str]:
    return ((relation.schema or "").lower(), relation.name.lower())


def _fingerprint_built(*, fingerprint: Fingerprint, target: MigrationRelation) -> bool:
    if fingerprint.target_name is None:
        return False
    return target.matches(
        MigrationRelation(
            database=fingerprint.target_database,
            schema=fingerprint.target_schema,
            name=fingerprint.target_name,
        )
    )


def _fingerprint_order(fingerprint: Fingerprint) -> tuple[object, str]:
    return (fingerprint.ts.isoformat(), fingerprint.run_id)
