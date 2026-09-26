<!-- generated-by: sqlbuild skills -->

# Model migrations

> Keep the history of an incremental or snapshot model when you rename it.

Online: https://sqlbuild.com/docs/concepts/models/migrations/

Renaming an incremental or snapshot model normally means rebuilding it from scratch under the new name, which loses any history the source data can no longer reproduce. A model migration moves the existing relation's data to the new name instead, then continues building incrementally.

Migrations apply to incremental and snapshot models.

## Declaring a migration

Add `migrate_from` to the renamed model's header, naming the old model:

```sql
MODEL (
  materialized incremental,
  migrate_from stg_orders,
  cursor order_date,
  ...
);
```

Use `schema.name` when the old relation is in a different schema of the same database.

On the next build, SQLBuild copies the old relation's data to the new name through a staging table (see [How a move runs](#how-a-move-runs)), records the move, and builds the model incrementally from the migrated state. There is no first-run rebuild, and no `replay_on_change` replay caused by the rename. The old relation is never modified or dropped. Once it is no longer part of the project, [janitor](../../cli/janitor.md) archives it like any other stale relation.

After the move is recorded, `migrate_from` has no further effect, and SQLBuild tells you it can be removed. Keep it until every target that needs the move has built.

## Decisions

`sqb plan` shows the decision for every migration:

| Decision | Meaning |
|----------|---------|
| `migrate` | The new relation doesn't exist. Move the old one's data to it. |
| `done` | The move is already recorded. Nothing to do. |
| `redo` | The new relation exists but has no build history and no recorded move, which is what an interrupted migration leaves behind. Move it again. |
| `superseded replace` | The new relation was itself the origin of the latest recorded move, for example after renaming a model back. Replace it with the newer data. |
| `forced replace` | The new relation has its own build history and `migrate_force true` is set. Replace it. |
| `conflict` | The new relation has its own build history. The build stops (`M103`) until you set `migrate_force true` or remove `migrate_from`. |
| `origin missing` | The old relation doesn't exist and no move was recorded. The build stops (`M102`). |

The origin and destination must be compatible under the model's normal `on_schema_change` rules; otherwise the build stops (`M104`).

`migrate_force true` only affects the `conflict` case and is safe to leave in the header.

## Automatic discovery

If a selected model has never been built, SQLBuild compares it with models that were removed from the project but whose relations still exist. When exactly one removed model has equivalent logic, it is migrated automatically. Equivalent means the same query and configuration, ignoring the model's own name, CTE and table alias names, comments, formatting, and storage-only settings. Renamed upstream models are matched first, so a renamed chain of models is migrated together. Removed models whose data was already moved on by a recorded migration are not candidates, so a model renamed several times matches its latest table.

Renamed tables and views are matched the same way. They are still rebuilt under the new name, since they hold no history, but they keep their identity for change detection, so incremental models downstream of a renamed view are not replayed or rebuilt. These renames are recorded as `renamed` events.

Automatic discovery never guesses. If a match is ambiguous, SQLBuild warns (`M107`) and builds from scratch; declare `migrate_from` to choose. An explicit `migrate_from` always wins. Automatic discovery covers renames within the project's schemas; use `migrate_from` to move a model to another schema. Relations last built before this feature carry no stored fingerprint and aren't matched automatically.

## How a move runs

A move never overwrites the destination directly:

1. The old relation is cloned or copied into a new staging table named `_sqb_archive__<UTC timestamp>__migration_stage__<name>`, with the destination's configured table type.
2. The staging table is checked: it must exist, have the expected columns and table type, and, for a physical copy, the same row count as the old relation.
3. The staging table is swapped in as the destination. If a destination already existed, for example after `superseded replace` or `forced replace`, it is kept as `_sqb_archive__<UTC timestamp>__migration_previous__<name>` rather than dropped.
4. The move is recorded, then the model builds as usual.

The old relation is never modified. Staging and replaced tables use the [janitor](../../cli/janitor.md) archive format, so an abandoned staging table or a replaced destination is deleted by janitor after `archive_retention_days`. A staging table left by an interrupted run is never reused; the next run stages again. Don't run janitor at the same time as a build in the same schema.

`sqb plan` shows how each move will run, for example `physical copy, transient -> permanent, promote by swap`.

## State

Each move is recorded in an append-only `_sqlbuild_migrations` table in the destination schema. A missing record means completion is unrecorded; staging or promotion may already have happened. Re-running after an interruption recovers through the migration decisions above.

## Adapter support

| Adapter | Staging | Promotion |
|---------|---------|-----------|
| Snowflake | Zero-copy clone with `COPY GRANTS`. Transient → permanent is a physical copy, because Snowflake can't clone a transient table into a permanent one. | `ALTER TABLE … SWAP WITH` for an existing destination; rename for a missing destination |
| BigQuery | `CREATE TABLE … CLONE`, or `CREATE TABLE … COPY` when BigQuery refuses the clone | Two renames; the destination is briefly missing between them, and an interrupted run recovers on retry |
| Databricks | `DEEP CLONE` | Two renames, as for BigQuery |
| PostgreSQL, SQL Server, DuckDB, MotherDuck | Physical copy | Renames and the migration record in one transaction |

On PostgreSQL, views that depend on the destination are re-pointed to the new table in the same transaction, keeping their options, owner and grants. Materialized views are not re-pointed.

## Previewing another target

`sqb plan --as <target>` compiles the project for another target, for example production, and shows its migration decisions using your current connection. It only inspects; nothing is written.
