<!-- generated-by: sqlbuild skills -->

# Model migrations

> Keep a renamed model's history, and keep its old name working for a while.

Online: https://sqlbuild.com/docs/concepts/models/migrations/

## Contents

- Declaring a migration
- Decisions
- Automatic discovery
- How a move runs
- Old names
- State
- Adapter support
- Previewing another target

Renaming an incremental or snapshot model normally means rebuilding it from scratch under the new name, which loses any history the source data can no longer reproduce. A model migration moves the existing relation's data to the new name instead, then continues building incrementally.

Table and view models can declare a migration too. They hold no history, so they are rebuilt under the new name, but they keep their identity for change detection. For every materialization, the old name keeps working for a while through a [compatibility view](#old-names). To keep a column's history when you rename the column, see [Column migrations](column-migrations.md).

## Declaring a migration

[`sqb rename`](../../cli/rename.md) renames a model and every reference to it, and adds `migrate_from` only when [automatic discovery](#automatic-discovery) would not find the old relation.

To declare a migration by hand, add `migrate_from` to the renamed model's header, naming the old model:

```sql
MODEL (
  materialized incremental,
  migrate_from stg_orders,
  cursor order_date,
  ...
);
```

Use `schema.name` when the old relation is in a different schema of the same database.

On the next build, SQLBuild copies the old relation's data to the new name through a staging table (see [How a move runs](#how-a-move-runs)), records the move, and builds the model incrementally from the migrated state. There is no first-run rebuild, and no `replay_on_change` replay caused by the rename. After the model builds, the old relation is archived and a compatibility view takes its name (see [Old names](#old-names)).

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

Table and view models only ever see `migrate`, `done`, and `origin missing`: nothing is replaced, so there is no conflict. `migrate_force` on a table or view model is a compile error. In `sqb plan --json`, their decision is `renamed`.

## Automatic discovery

If a selected model has never been built, SQLBuild compares it with models that were removed from the project but whose relations still exist. When exactly one removed model has equivalent logic, it is migrated automatically. Equivalent means the same query and configuration, ignoring the model's own name, CTE and table alias names, comments, formatting, and storage-only settings. Renamed upstream models are matched first, so a renamed chain of models is migrated together. Removed models whose data was already moved on by a recorded migration are not candidates, so a model renamed several times matches its latest table.

Renamed tables and views are matched the same way. They are rebuilt under the new name, since they hold no history, but they keep their identity for change detection, so incremental models downstream of a renamed view are not replayed or rebuilt. These renames are recorded as `renamed` events.

Automatic discovery never guesses. If a match is ambiguous, SQLBuild warns (`M107`) and builds from scratch; declare `migrate_from` to choose. An explicit `migrate_from` always wins. Automatic discovery covers renames within the project's schemas; use `migrate_from` to move a model to another schema. Relations last built before this feature carry no stored fingerprint and aren't matched automatically.

## How a move runs

A move never overwrites the destination directly:

1. The old relation is cloned or copied into a new staging table named `_sqb_archive__<UTC timestamp>__migration_stage__<name>`, with the destination's configured table type.
2. The staging table is checked: it must exist, have the expected columns and table type, and, for a physical copy, the same row count as the old relation.
3. The staging table is swapped in as the destination. If a destination already existed, for example after `superseded replace` or `forced replace`, it is kept as `_sqb_archive__<UTC timestamp>__migration_previous__<name>` rather than dropped.
4. The move is recorded, then the model builds as usual.
5. After the model builds successfully, the old relation is archived and a compatibility view is created at its name (see [Old names](#old-names)).

Until step 5, the old relation is not modified. Staging and replaced tables use the [janitor](../../cli/janitor.md) archive format, so an abandoned staging table or a replaced destination is deleted by janitor after `archive_retention_days`. A staging table left by an interrupted run is never reused; the next run stages again. Don't run janitor at the same time as a build in the same schema.

`sqb plan` shows how each move will run, for example `physical copy, transient -> permanent, promote by swap`.

## Old names

A rename breaks every query outside the project that still reads the old name: dashboards, notebooks, other teams' jobs. After the renamed model builds successfully, SQLBuild keeps the old name working for a while:

1. The old relation is renamed to `_sqb_archive__<UTC timestamp>__migration_origin__<name>`.
2. A view is created at the old name that selects from the new relation.
3. The view gets the privileges that were granted on the old relation, read from the archive. Only existing grants are copied; nothing new is granted.

On DuckDB, MotherDuck, PostgreSQL, and SQL Server these steps and their records commit in one transaction. On Snowflake, BigQuery, and Databricks each step is recorded after it runs, and a re-run resumes from the first unrecorded step without repeating one. A failure is reported as `M117`; re-run the build.

| Adapter | Privileges copied to the view |
|---------|-------------------------------|
| Snowflake | `SHOW GRANTS` on the archive, replayed to roles and database roles, keeping `WITH GRANT OPTION`. `OWNERSHIP`, grants to shares, and privileges that don't apply to views are skipped |
| PostgreSQL | Table and column privileges from the catalog, including grants to `PUBLIC` and `WITH GRANT OPTION`. The owner's own privileges are not copied |
| BigQuery | Table IAM role bindings from `INFORMATION_SCHEMA.OBJECT_PRIVILEGES`, replayed with `GRANT`. See the note below |
| Databricks | Unity Catalog grants on the table itself that apply to views, such as `SELECT`. `OWN`, `MODIFY`, and inherited catalog or schema grants are skipped |
| SQL Server | Object and column permissions, including `DENY` and `WITH GRANT OPTION`, that apply to views |
| DuckDB, MotherDuck | No object privileges exist |

Column privileges are copied to the view's column of the same name, which is the old name when the view aliases a renamed column. A column privilege on a column the view no longer exposes is not copied; the view shows nothing of that column.

The copied grants are recorded on the view's creation. After that, the view's own privileges are what counts: when SQLBuild redefines the view after a rebuild, the view ends up with exactly the privileges it had just before, so a privilege you revoke from the view stays revoked and one you grant on the view is kept. SQLBuild uses `CREATE OR REPLACE VIEW` on PostgreSQL, `COPY GRANTS` on Snowflake, and `ALTER VIEW` on SQL Server and Databricks.

Creating or replacing a view can also apply privileges you did not give it: PostgreSQL applies `ALTER DEFAULT PRIVILEGES` when it re-creates a view, and Snowflake applies the schema's future grants for views on `CREATE OR REPLACE VIEW … COPY GRANTS`. SQLBuild reads the view's privileges before every create or redefinition and reconciles afterwards: it grants what went missing and revokes what was added. A new compatibility view likewise ends up with only the privileges copied from the old relation. Ownership and the owner's own privileges are never changed.

A recorded view that no longer exists at the old name is not re-created by a build; [janitor](../../cli/janitor.md) records it as dropped.

On Snowflake, BigQuery, Databricks, DuckDB, and MotherDuck, views read their tables by name when queried, so a build redefines a compatibility view only when its SQL would change, for example when the view lists columns and the new relation's columns changed. PostgreSQL views are bound to the table itself, so they are redefined whenever the table is replaced.

BigQuery cannot rename views, so an old view model is re-created under the archive name with its IAM bindings, and then dropped.

On BigQuery, a view reads its tables with the permissions of whoever queries it. A principal that could read the old table keeps access to the old name through the copied bindings, but also needs read access on the new table. SQLBuild does not grant that and does not create authorized views; the build warns with `M118` and names the principals.

If columns were renamed, the view presents them under their old names, for example `SELECT order_id, revenue AS amount FROM analytics.daily_revenue`. Incremental and snapshot models alias every recorded [column migration](column-migrations.md). A table or view model that declares `migrate_from` can declare old column names the same way, as `revenue (migrate_from amount)`; this only aliases the column in the compatibility view, since the table is rebuilt with the new name anyway. The view follows the new relation's current columns after every build of the model.

`sqb plan` shows what happens at the old name:

```
Migrations (1)
└── daily_revenue  migrate  analytics.revenue -> analytics.daily_revenue
    ├── transfer  rebuild (table)
    └── old name  analytics.revenue
        ├── view  until 2026-10-28
        ├── columns  amount <- revenue
        ├── grants  copied from the old table
        └── old table  archived
```

A move resumed after the archive shows `old table  already archived`. Once the view exists it shows `view  live until 2026-10-28` and how many grants were copied. When no view is kept, the block shows `left for janitor` and the reason, such as `old_name_view false` or `name reused by model:revenue`.

In `sqb plan --json`, each migration has an `old_name` object with `action` (`archive_and_view`, `view_only`, `live`, or `none`), `view`, `reads`, `expires_at`, `column_aliases`, `grants_copied` (the number of grants copied once the view exists, otherwise `null`), and `reason`. The top-level `old_names` list also includes steps that resume an earlier move.

The view expires after 30 days by default. After that, [janitor](../../cli/janitor.md) drops it; `sqb janitor --drop-old-name-view analytics.revenue` drops it earlier. Change the default for the project, or turn the views off with `false`:

```toml
[migrations]
old_name_views = "7d"
```

A model header overrides the project setting with `old_name_view 7d` or `old_name_view false`. The retention of a move is fixed when the move is recorded.

With views off, or when a view can't be kept, the old relation is left in place and janitor archives it once it is no longer part of the project, as before. No view is created when:

- the old relation was not built by SQLBuild;
- another model in the project builds at the old name;
- the old name is itself a compatibility view of an earlier rename.

Moves recorded before a SQLBuild version that supports old-name views never gain a view later.

### Code inside the project

The compatibility view is for consumers outside the project. Project code must use the new model:

- Python nodes, hooks, and loaders whose literal SQL names the old name fail with `P008`, at compile time for a declared `migrate_from` and at plan time for an automatically discovered rename. SQL models reading it through `__ref` are unaffected, since `__ref` resolves the new name.
- A new model whose name is a live compatibility view stops the build with `M114`, which names the view and its expiry. Drop the view early with janitor, or choose another name.

### PostgreSQL views

PostgreSQL views are bound to the table they read, not its name. When a build replaces the renamed model's table, or drops or retypes its columns, SQLBuild points its compatibility views at the new table in the same transaction, so they are never missing, even if the build is interrupted. A view is replaced in place when its columns allow it, so views you build on top of the compatibility view keep working; otherwise it is dropped and re-created with the privileges it had, which fails if another view depends on it.

Views outside SQLBuild that read the old relation follow it into the archive and keep reading its old data; the build warns with `M115` and names them. Re-create them against the old name or the new relation. On the other adapters, views read relations by name, so no rebinding is needed.

### Upgrading

Upgrade the SQLBuild version that runs `sqb janitor` together with the one that runs builds. An older janitor does not know compatibility views and archives them as stale relations.

## State

Each move is recorded in an append-only `_sqlbuild_migrations` table in the destination schema. A missing record means completion is unrecorded; staging or promotion may already have happened. Re-running after an interruption recovers through the migration decisions above.

What happens at the old name is recorded in an append-only `_sqlbuild_old_name_views` table next to it, one row per step: `required` (with the move), `origin_archived`, `view_created`, and `view_dropped`. Rows are never updated.

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
