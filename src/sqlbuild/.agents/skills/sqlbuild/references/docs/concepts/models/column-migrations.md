<!-- generated-by: sqlbuild skills -->

# Column migrations

> Keep a column's history when you rename it in an incremental or snapshot model.

Online: https://sqlbuild.com/docs/concepts/models/column-migrations/

## Contents

- Declaring a rename
- Automatic detection
- Decisions
- How a rename runs
- State
- Adapter support

`on_schema_change` compares columns by name, so renaming a column looks like one column removed and another added. With the default `append_new_columns`, the new column starts empty and older rows keep their values under the old name; with `sync_all_columns`, the old column and its data are dropped. A column migration renames the column in the warehouse instead, so every row keeps its value under the new name, with no leftover column and no replay.

Column migrations apply to incremental models, including microbatch models, and snapshot models. Tables and views are rebuilt on every change and don't need them.

## Declaring a rename

[`sqb rename <model>.<column>`](../../cli/rename.md) renames the column in the model and every query that reads it, and adds the `migrate_from` declaration below for you.

Add `migrate_from` to the renamed column in the model header, naming the old column:

```sql
MODEL (
  description "One row per order",
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key order_id,
  cursor order_date,
  columns (
    revenue (migrate_from amount),
  ),
);

SELECT order_id, order_date, amount AS revenue
FROM __source("raw_orders")
```

On the next build, SQLBuild renames `amount` to `revenue` in the existing table, records the rename, and then builds the model incrementally, so the new delta lands in `revenue`.

A column entry may contain only `migrate_from`, or combine it with `type`, `nullable`, `description`, and `audits`. When the model binds a reusable schema with `model_schema`, an inherited column may add `migrate_from` without redeclaring its metadata.

After the rename is recorded, `migrate_from` has no further effect, and SQLBuild reports (`M108`) that it can be removed. Keep it until every target that needs the rename has built. On a target where the table doesn't exist yet, the declaration does nothing: the table is created with the new column name.

A declaration is rejected when compiling if:

- the model is not incremental or snapshot, unless it is a table or view model that declares its own `migrate_from`; there the column's `migrate_from` only names the old column in the [compatibility view](migrations.md#old-names) at the model's old name;
- `migrate_from` names the column itself, or a qualified name instead of one column;
- two columns declare the same `migrate_from`;
- a declared column migrates from another column that itself declares `migrate_from`. Chains and swaps can't be renamed in place safely; rename through a name no other column uses, or rebuild with `--full-refresh`.

## Automatic detection

A pure rename is detected without a declaration: exactly one column that disappeared from the model has exactly the same expression as exactly one new column, for example `amount` becoming `amount AS revenue`, or `ROUND(amount, 2) AS revenue` becoming `ROUND(amount, 2) AS net_revenue`. Expressions are compared ignoring formatting, comments, and keyword and unquoted identifier case. Detection compares the query the table was last built from with the current query, so it applies to the build that makes the change.

A rename is only automatic when it is the whole change. Apart from the renamed output names, the query must be the same: the same CTEs, `FROM`, joins, filters, grouping, and other columns. References to the new name in `ORDER BY` or `QUALIFY` count as references to the old name only when SQLBuild can prove they bind to the output column: the columns of every relation the query reads must be known, from the inspected warehouse tables of its sources and upstream models or from CTEs and subqueries with named columns, the new name must not be an input column, and the old name must either not be an input column or be passed through unchanged. Otherwise the change is not treated as a rename, because engines differ on whether such a name refers to the output alias or the input column. The output columns may be reordered unless the query groups, orders, or uses `DISTINCT ON` by position. If anything else changed, an unchanged expression such as `amount` may now read different data, for example from a CTE that redefines `amount`, so nothing is renamed automatically and the change follows `on_schema_change`. Declare `migrate_from` to rename the column anyway.

Detection never guesses:

- Columns are matched by expression, not by position. Two columns renamed at once each pair with the column whose expression they kept; two columns that swap names keep their names and are not renamed.
- If more than one removed column has the same expression, or more than one new column does, nothing is migrated automatically.
- A near match, where the expressions reference the same columns but differ or the rest of the query changed, for example `amount` becoming `ROUND(amount, 2) AS revenue`, is not a rename. It follows the model's `on_schema_change` policy, and `sqb plan` shows a hint next to the added column until the change has been built:

```text
    ├── schema diff:
      + revenue   (added)
        similar to amount; if this is a rename, add revenue (migrate_from amount)
      - amount   (removed)
```

Add the suggested `migrate_from` to keep the history. A declared rename with a changed expression or other query changes is still renamed in place, but it is a query change, so `replay_on_change` decides how much history is rebuilt, exactly as it would without the rename.

## Decisions

`sqb plan` and `sqb build` list column migrations before the models they change:

```text
Column migrations (1)
└── fact_orders  migrate columns
    └── amount -> revenue  rename in place
```

Automatically detected renames are marked `(automatic)`. The decision is based on the table's current columns first, then on recorded renames:

| Decision | Meaning |
|----------|---------|
| `rename in place` | The old column exists and the new one doesn't. Rename it. |
| `already renamed, record` | The new column exists and the old one doesn't, but no rename is recorded, which is what an interrupted rename leaves behind. Record it without renaming again. |
| `done` | The rename is recorded and the new column exists. Nothing to do. |
| `conflict` | Both columns exist. The build stops (`M110`); drop one of them, or remove `migrate_from` and let `on_schema_change` handle the columns. |
| `source missing` | Neither column exists and no rename is recorded. The plan warns (`M109`) and the columns follow `on_schema_change` as if `migrate_from` were absent. A target can require confirmation or stop the build instead with [`missing_migration_origin`](../project-configuration.md#missing-migration-origins). |
| `source still produced` | The query still selects the old column. The build stops (`M111`). |
| `unsupported` | The warehouse can't rename this table's columns in place (see [Adapter support](#adapter-support)). The build stops (`M112`). |

Automatically detected renames never stop a build: when they can't be applied, the columns follow `on_schema_change` as before.

## How a rename runs

Renames run after [model migrations](migrations.md) and before any model builds, one model at a time:

1. The table's current columns are read again. A column that is already renamed is not renamed twice.
2. The column is renamed with `ALTER TABLE ... RENAME COLUMN` or the adapter's equivalent.
3. The rename is recorded.

On adapters with transactional DDL (PostgreSQL, SQL Server, DuckDB, MotherDuck), each model's renames and their records commit together. On other adapters, a build interrupted between the rename and the record is recovered by the `already renamed, record` decision on the next build. A build that fails after the rename, for example while applying the delta, resumes on the next build without renaming again.

After the rename, the remaining differences follow `on_schema_change`: `append_new_columns` adds any other new columns, `sync_all_columns` also drops removed ones and changes types, and `fail` only fails when a difference other than the rename remains.

A pure rename is not a query change. This applies to declared renames too, as long as the rename is the whole change by the rule above. It doesn't trigger `replay_on_change` for the model, and it doesn't cascade a replay to downstream models. Downstream models that you edit to use the new name have query changes of their own and follow their own `replay_on_change`. If the renamed column is the model's cursor, the next delta starts from the watermark stored under the old name.

## State

Each rename is recorded in an append-only `_sqlbuild_column_migrations` table in the model's schema, with the model, relation, old and new column, discovery (`manual` or `automatic`), and decision (`rename` or `record`). Janitor never archives it.

## Adapter support

| Adapter | Statement |
|---------|-----------|
| Snowflake, PostgreSQL, DuckDB, MotherDuck, BigQuery | `ALTER TABLE ... RENAME COLUMN ... TO ...` |
| Databricks | `ALTER TABLE ... RENAME COLUMN ... TO ...`, which requires Delta column mapping |
| SQL Server | `EXEC sp_rename '<schema>.<table>.<column>', '<new name>', 'COLUMN'` |

Databricks renames a Delta table column only when the table uses name-based column mapping (`delta.columnMapping.mode = 'name'`). SQLBuild checks this during planning and doesn't change the table protocol for you. A declared rename on a table without column mapping stops the build (`M112`) with the statement that enables it:

```sql
ALTER TABLE <table> SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.minReaderVersion' = '2',
  'delta.minWriterVersion' = '5'
);
```

Enabling column mapping upgrades the table's Delta protocol, which older readers may not support. An automatically detected rename on such a table is skipped with a warning (`M112`) and follows `on_schema_change`.

On PostgreSQL, views that select the renamed column keep working and keep their own output column names. On SQL Server, `sp_rename` warns that renaming can break scripts and stored procedures that reference the old name. On PostgreSQL, the new name is created in lower case, as an unquoted identifier would be.
