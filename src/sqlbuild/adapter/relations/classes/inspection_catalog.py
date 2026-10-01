"""Invocation-scoped warehouse metadata shared by every planning inspection phase."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.relations._helpers.inspection_context import emit_inspection_record
from sqlbuild.adapter.relations.constants import (
    INSPECTION_DESCRIBED_NAME_LIMIT,
    INSPECTION_IN_LIST_LIMIT,
)
from sqlbuild.adapter.relations.main.run_bounded_inspections import run_bounded_inspections
from sqlbuild.adapter.relations.models import (
    InspectionQueryRecord,
    SchemaColumnListing,
    SchemaRelationListing,
)
from sqlbuild.adapter.relations.types import SchemaScopedMetadataReader

type _RelationIdentity = tuple[str | None, str | None, str]
type _SchemaKey = tuple[str | None, str]
type _RelationRequestKey = tuple[str | None, tuple[str, ...] | None, tuple[str, ...] | None]


class InspectionCatalog:
    """Read each schema's metadata at most once per planning invocation, filtering client-side."""

    def __init__(self, *, adapter: Any, connection: Any) -> None:
        self.adapter: Any = adapter
        self.connection: Any = connection
        self._reader: SchemaScopedMetadataReader | None = (
            adapter if isinstance(adapter, SchemaScopedMetadataReader) else None
        )
        self._concurrency: int = max(1, int(getattr(adapter, "metadata_inspection_concurrency", 1)))
        self._relation_listings: dict[_SchemaKey, SchemaRelationListing] = {}
        self._column_listings: dict[_SchemaKey, SchemaColumnListing] = {}
        self._relation_requests: dict[_RelationRequestKey, tuple[RelationInfo, ...]] = {}
        self._relation_columns: dict[_RelationIdentity, tuple[ColumnInfo, ...] | None] = {}

    @property
    def concurrency(self) -> int:
        """Return the bounded number of concurrent reads this adapter supports."""

        return self._concurrency

    def cached_relation_listing(
        self, *, database: str | None, schema: str
    ) -> SchemaRelationListing | None:
        """Return a schema listing already read in this invocation, without reading."""

        return self._relation_listings.get(self._schema_key(database=database, schema=schema))

    def list_relations(
        self,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        """Return the relations ``adapter.list_relations`` would return for this request."""

        if self._reader is None or not schemas:
            return self._list_relations_directly(database=database, schemas=schemas, names=names)
        unique_schemas: tuple[str, ...] = tuple(dict.fromkeys(schemas))
        self.prefetch_relation_listings(database=database, schemas=unique_schemas)
        wanted: frozenset[str] | None = (
            None if names is None else frozenset(self._reader.metadata_name_key(n) for n in names)
        )
        relations: list[RelationInfo] = []
        schema: str
        for schema in unique_schemas:
            listing: SchemaRelationListing = self._relation_listings[
                self._schema_key(database=database, schema=schema)
            ]
            relations.extend(
                entry.relation
                for entry in listing.entries
                if wanted is None or entry.stored_name in wanted
            )
        return tuple(relations)

    def prefetch_relation_listings(self, *, database: str | None, schemas: tuple[str, ...]) -> None:
        """Read every not-yet-listed schema of one database concurrently."""

        self.prefetch_schema_listings(scopes=tuple((database, schema) for schema in schemas))

    def prefetch_schema_listings(
        self, *, scopes: tuple[tuple[str | None, str], ...], best_effort: bool = False
    ) -> None:
        """Read unlisted schemas concurrently; best-effort failures stay uncached for re-read."""

        reader: SchemaScopedMetadataReader | None = self._reader
        if reader is None:
            return
        missing: dict[_SchemaKey, tuple[str | None, str]] = {}
        database: str | None
        schema: str
        for database, schema in scopes:
            key: _SchemaKey = self._schema_key(database=database, schema=schema)
            if key not in self._relation_listings:
                missing.setdefault(key, (database, schema))
        listings: list[SchemaRelationListing | None] = run_bounded_inspections(
            tasks=tuple(
                self._bind_relation_listing(
                    reader=reader, database=database, schema=schema, best_effort=best_effort
                )
                for database, schema in missing.values()
            ),
            concurrency=self._concurrency,
        )
        missing_key: _SchemaKey
        listing: SchemaRelationListing | None
        for missing_key, listing in zip(missing, listings, strict=True):
            if listing is not None:
                self._relation_listings[missing_key] = listing

    def get_columns_for_relations(
        self, *, relations: tuple[RelationInfo, ...]
    ) -> dict[_RelationIdentity, tuple[ColumnInfo, ...]]:
        """Return the columns ``adapter.get_columns_for_relations`` would return."""

        unique: dict[_RelationIdentity, RelationInfo] = {}
        relation: RelationInfo
        for relation in relations:
            unique.setdefault(relation.identity, relation)
        missing: tuple[RelationInfo, ...] = tuple(
            relation
            for identity, relation in unique.items()
            if identity not in self._relation_columns
        )
        if missing:
            if self._reader is None:
                self._read_columns_directly(relations=missing)
            else:
                self._read_columns_by_schema(reader=self._reader, relations=missing)
        result: dict[_RelationIdentity, tuple[ColumnInfo, ...]] = {}
        identity: _RelationIdentity
        for identity in unique:
            columns: tuple[ColumnInfo, ...] | None = self._relation_columns.get(identity)
            if columns is not None:
                result[identity] = columns
        return result

    def _list_relations_directly(
        self,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None,
    ) -> tuple[RelationInfo, ...]:
        key: _RelationRequestKey = (
            database,
            None if schemas is None else tuple(schemas),
            None if names is None else tuple(names),
        )
        cached: tuple[RelationInfo, ...] | None = self._relation_requests.get(key)
        if cached is not None:
            return cached
        relations: tuple[RelationInfo, ...]
        if self._reader is not None and names is not None and len(names) > INSPECTION_IN_LIST_LIMIT:
            unique_names: tuple[str, ...] = tuple(dict.fromkeys(names))
            chunks: tuple[tuple[str, ...], ...] = tuple(
                unique_names[start : start + INSPECTION_IN_LIST_LIMIT]
                for start in range(0, len(unique_names), INSPECTION_IN_LIST_LIMIT)
            )
            chunk_results: list[tuple[RelationInfo, ...]] = run_bounded_inspections(
                tasks=tuple(
                    self._bind_direct_listing(database=database, schemas=schemas, names=chunk)
                    for chunk in chunks
                ),
                concurrency=self._concurrency,
            )
            relations = _flatten_relations(chunk_results)
        else:
            relations = self._bind_direct_listing(database=database, schemas=schemas, names=names)()
        self._relation_requests[key] = relations
        return relations

    def _bind_direct_listing(
        self,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None,
    ) -> Callable[[], tuple[RelationInfo, ...]]:
        def list_directly() -> tuple[RelationInfo, ...]:
            started: float = time.monotonic()
            relations: tuple[RelationInfo, ...] = self.adapter.list_relations(
                connection=self.connection, database=database, schemas=schemas, names=names
            )
            emit_inspection_record(
                record=InspectionQueryRecord(
                    sql=(
                        f"list_relations(database={database}, "
                        f"schemas={_describe(schemas)}, names={_describe(names)})"
                    ),
                    elapsed_seconds=time.monotonic() - started,
                    row_count=len(relations),
                )
            )
            return relations

        return list_directly

    def _bind_relation_listing(
        self,
        *,
        reader: SchemaScopedMetadataReader,
        database: str | None,
        schema: str,
        best_effort: bool = False,
    ) -> Callable[[], SchemaRelationListing | None]:
        def read_listing() -> SchemaRelationListing | None:
            try:
                return reader.read_schema_relation_listing(
                    connection=self.connection, database=database, schema=schema
                )
            except Exception:
                if best_effort:
                    return None
                raise

        return read_listing

    def _read_columns_directly(self, *, relations: tuple[RelationInfo, ...]) -> None:
        started: float = time.monotonic()
        columns: dict[_RelationIdentity, tuple[ColumnInfo, ...]] = (
            self.adapter.get_columns_for_relations(connection=self.connection, relations=relations)
        )
        emit_inspection_record(
            record=InspectionQueryRecord(
                sql=f"get_columns_for_relations(relations={len(relations)})",
                elapsed_seconds=time.monotonic() - started,
                row_count=sum(len(value) for value in columns.values()),
            )
        )
        relation: RelationInfo
        for relation in relations:
            self._relation_columns[relation.identity] = columns.get(relation.identity)

    def _read_columns_by_schema(
        self, *, reader: SchemaScopedMetadataReader, relations: tuple[RelationInfo, ...]
    ) -> None:
        unscoped: list[RelationInfo] = []
        by_schema: dict[_SchemaKey, list[RelationInfo]] = {}
        relation: RelationInfo
        for relation in relations:
            if relation.schema is None:
                unscoped.append(relation)
                continue
            by_schema.setdefault(
                self._schema_key(database=relation.database, schema=relation.schema), []
            ).append(relation)
        if unscoped:
            self._read_columns_directly(relations=tuple(unscoped))
        listing_keys: list[_SchemaKey] = []
        listing_tasks: list[Callable[[], SchemaColumnListing]] = []
        exact_relations: list[RelationInfo] = []
        schema_key: _SchemaKey
        scoped: list[RelationInfo]
        for schema_key, scoped in by_schema.items():
            if schema_key in self._column_listings:
                continue
            if len(scoped) <= reader.exact_column_inspection_limit:
                exact_relations.extend(scoped)
                continue
            listing_keys.append(schema_key)
            listing_tasks.append(
                self._bind_column_listing(
                    reader=reader, database=scoped[0].database, schema=scoped[0].schema or ""
                )
            )
        exact_tasks: list[Callable[[], tuple[ColumnInfo, ...]]] = [
            self._bind_relation_columns(reader=reader, relation=exact) for exact in exact_relations
        ]
        results: list[SchemaColumnListing | tuple[ColumnInfo, ...]] = run_bounded_inspections(
            tasks=(*listing_tasks, *exact_tasks), concurrency=self._concurrency
        )
        listing: SchemaColumnListing | tuple[ColumnInfo, ...]
        for schema_key, listing in zip(listing_keys, results[: len(listing_keys)], strict=True):
            if isinstance(listing, SchemaColumnListing):
                self._column_listings[schema_key] = listing
        exact: RelationInfo
        exact_columns: SchemaColumnListing | tuple[ColumnInfo, ...]
        for exact, exact_columns in zip(exact_relations, results[len(listing_keys) :], strict=True):
            if not isinstance(exact_columns, SchemaColumnListing):
                self._relation_columns[exact.identity] = exact_columns
        for schema_key, scoped in by_schema.items():
            column_listing: SchemaColumnListing | None = self._column_listings.get(schema_key)
            if column_listing is None:
                continue
            for relation in scoped:
                self._relation_columns[relation.identity] = (
                    column_listing.columns_by_stored_name.get(
                        reader.metadata_name_key(relation.name)
                    )
                )

    def _bind_column_listing(
        self, *, reader: SchemaScopedMetadataReader, database: str | None, schema: str
    ) -> Callable[[], SchemaColumnListing]:
        def read_listing() -> SchemaColumnListing:
            return reader.read_schema_column_listing(
                connection=self.connection, database=database, schema=schema
            )

        return read_listing

    def _bind_relation_columns(
        self, *, reader: SchemaScopedMetadataReader, relation: RelationInfo
    ) -> Callable[[], tuple[ColumnInfo, ...]]:
        def read_columns() -> tuple[ColumnInfo, ...]:
            return reader.read_relation_columns(connection=self.connection, relation=relation)

        return read_columns

    def _schema_key(self, *, database: str | None, schema: str) -> _SchemaKey:
        if self._reader is None:
            return (database, schema)
        return (
            None if database is None else self._reader.metadata_name_key(database),
            self._reader.metadata_name_key(schema),
        )


def _flatten_relations(chunks: list[tuple[RelationInfo, ...]]) -> tuple[RelationInfo, ...]:
    relations: list[RelationInfo] = []
    chunk: tuple[RelationInfo, ...]
    for chunk in chunks:
        relations.extend(chunk)
    return tuple(relations)


def _describe(values: tuple[str, ...] | None) -> str:
    if values is None:
        return "*"
    if len(values) <= INSPECTION_DESCRIBED_NAME_LIMIT:
        return "[" + ", ".join(values) + "]"
    return f"[{len(values)} names]"
