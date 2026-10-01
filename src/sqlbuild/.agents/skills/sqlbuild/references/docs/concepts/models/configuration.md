<!-- generated-by: sqlbuild skills -->

# Configuration

> MODEL() header fields and SQL-analysis controls.

Online: https://sqlbuild.com/docs/concepts/models/configuration/

## Contents

- Common fields
- SQL analysis
- Table fields
- Incremental fields
- Snapshot fields
- Custom materialization fields
- Diff fields

Every `MODEL()` key must be one of the fields on this page. Any other key fails compilation with
`D002`, naming the key and its file and line and suggesting the nearest supported key. SQL comments
(`-- ...` and `/* ... */`) inside a header are ignored:

```text
error[D002]: MODEL() in 'models/fct_orders.sql:3' has unsupported keys: descripton
  = help: did you mean 'description'?
```

`[defaults]` and `[path_defaults.*]` in `sqlbuild_project.toml` reject unknown keys in the same way
with `D001`. Values that a custom materialization reads belong inside its `config (...)` block,
which accepts any keys.

## Common fields

| Field | Description |
|-------|-------------|
| `materialized` | `view`, `table`, `incremental`, `snapshot`, or a custom materialization name |
| `tags` | Tags used by selectors |
| `description` | Human-readable model description |
| `columns` | Model-local column declarations, inherited-column audit augmentation, or column renames with `migrate_from` (incremental and snapshot models; see [Column migrations](column-migrations.md)). On a table or view model that declares its own `migrate_from`, a column `migrate_from` only names the old column in the [compatibility view](migrations.md#old-names) |
| `model_schema` | Reusable column schema name |
| `audits` | Model-level audit instances |
| `enums` | Model-local enum declarations; names must begin with `_` |
| `constants` | Model-local scalar, list, set, or object constants; names must begin with `_`. Use `constant(...)` for an explicit decimal type or collection rendering override. |
| `schema` | Destination warehouse schema override |
| `database` | Destination database override |
| `alias` | Destination relation-name override |
| `pre_hooks` | Ordered `inline_sql(...)`, `sql("name", ...)`, or `python("name", ...)` hooks before materialization |
| `post_hooks` | Ordered `inline_sql(...)`, `sql("name", ...)`, or `python("name", ...)` hooks after materialization |
| `enabled` | Set to `false` to disable the model |
| `contract` | `none` for an open statically checked declaration, or `enforced` for an exact declaration |
| `sql_analysis` | Per-model SQL-analysis override |
| `dynamic_columns` | Named pivot column families with `pivot_column`, `value_column`, `aggregate`, `type`, and `name_pattern` |
| `audit_factories` | Audit factories that generate audit cases for this model; see [Audits](../audits.md) |

## SQL analysis

SQL analysis has project, invocation, and model gates:

1. `settings.sql_analysis` must be enabled.
2. `--no-sql-analysis` must not be present.
3. `MODEL (sql_analysis false)` can disable analysis for that model. If omitted, the project setting
   is used.

A model cannot re-enable analysis when either broader gate disables it. The older `sql_validation`
and `--no-sql-validation` spellings remain compatibility aliases; use `sql_analysis` for new
configuration.

### Requiring SQL analysis

A project can stop opt-outs from hiding real findings:

```toml
# sqlbuild_project.toml
[settings]
require_sql_analysis = true   # default false
```

With this setting, `sql_analysis false` from a MODEL header or a `[path_defaults]` entry is accepted
only on a model whose SQL the parser cannot read: its query or one of its SQL hooks. On a model that
parses, compile reports a `P009`
error at the header key or `[path_defaults]` entry, with the findings the opt-out was hiding counted
by kind:

```text
error[P009]: `sql_analysis false` is not needed for model 'orders_summary'
  --> models/marts/orders_summary.sql:4:3
  = note: sqlbuild_project.toml sets [settings] require_sql_analysis = true, which only allows `sql_analysis false` on SQL that SQLBuild cannot parse; this model parses successfully.
  = help: remove `sql_analysis false` and fix the findings it was hiding: 2 unknown columns, 1 type mismatch (run `sqb compile` to see them)
  = help: to allow `sql_analysis false` on any model, SQL test or audit, set this in sqlbuild_project.toml:
            [settings]
            require_sql_analysis = false
```

`TEST(...)` and `AUDIT(...)` headers (singular and generic audits) also accept
`sql_analysis false`, which skips compile-time SQL checks on that test or audit; the SQL still runs.
SQL tests of a model with `sql_analysis false`, and audits attached to it, are not analysed either.
`require_sql_analysis = true` applies the same rule to these headers: the opt-out is accepted only
when that test or audit SQL cannot be parsed, otherwise compile reports `P009` at the header key.

`[settings] sql_analysis = false` in `sqlbuild_local.toml` is then a `D001` error, and
`require_sql_analysis` itself can only be set in `sqlbuild_project.toml`. `--no-sql-analysis` still
turns analysis off for one run, including the checks on audits, SQL tests and SQL hooks.

When the parser cannot read a model, the `P001` syntax error shows the exact MODEL header entry
(`sql_analysis false,`) and asks you to report the SQL so the parser can support it.

## Table fields

| Field | Description |
|-------|-------------|
| `table_type` | Snowflake table type: `permanent`, `transient`, or `inherit` |
| `time_travel_retention` | Managed time travel retention such as `7d`, `inherit`, or `disabled` |
| `run_despite_unchanged` | Removed with virtual environments. It is rejected in MODEL headers, project defaults, and path defaults. |

Table promotion mode is a project setting rather than a `MODEL()` field. Staged promotion is the default. Immediate promotion is incompatible with model type enforcement and exact contracts; see [Materializations](materializations.md#table).

## Incremental fields

| Field | Description |
|-------|-------------|
| `incremental_strategy` | `append`, `delete_insert`, or `merge` |
| `cursor` | Output column used to track incremental position |
| `cursor_type` | `timestamp` or `integer` |
| `cursor_grain` | Timestamp grain such as `second`, `hour`, or `day` |
| `cursor_start` | Lower cursor bound |
| `cursor_end` | Upper cursor bound |
| `cursor_start_max_ahead` | Largest distance a discovered automatic start may sit ahead of the invocation time, or `disabled` |
| `cursor_start_max_action` | `cap` or `error` when the start exceeds `cursor_start_max_ahead` |
| `cursor_future_max_distance` | Largest distance a discovered cursor watermark may sit in the future, or `disabled` |
| `cursor_future_action` | `cap` or `error` when a watermark exceeds `cursor_future_max_distance` |
| `cursor_inputs` | Upstream names mapped to cursor columns |
| `unique_key` | Merge or delete/insert matching columns |
| `incremental_mode` | Set to `microbatch` for batched execution |
| `microbatch_strategy` | Required in microbatch mode: `watermark` or `rolling_window` |
| `cursor_watermark_mode` | Watermark strategy policy: `all` or `any` |
| `batch_size` | Timestamp duration string such as `1d` or `1h`; use a numeric string such as `"1000"` for an integer cursor |
| `batch_concurrency` | Concurrent batch workers; values above `1` require `delete_insert` and the project concurrency gate |
| `microbatch_limit` | Nested `max_batches` and `action` policy for watermark execution |
| `max_microbatches` | Legacy scalar batch-count guard; use `microbatch_limit` for new models |
| `unaccounted_partition_policy` | Handling for microbatch partitions with no recorded completion: `synthesize`, `recover_empty`, or `recover_all` |
| `lookback` | Backward replay extension |
| `append_cursor_inclusive` | Include (`true`, default) or exclude (`false`) the current append-cursor boundary |
| `merge_exclude_columns` | Columns left unchanged by matched-row merge updates |
| `full_refresh` | Optional model execution override: `false` always runs incrementally, `true` always full-refreshes, and omission follows the command |
| `on_schema_change` | `append_new_columns`, `sync_all_columns`, `ignore`, or `fail` |
| `replay_on_change` | `forward`, `full`, or `bounded-<duration>` |
| `migrate_from` | Old model name (or `schema.name`) whose data this model takes over; see [Model migrations](migrations.md). Also valid on snapshot, table, and view models |
| `migrate_force` | `true` replaces a destination that already has its own build history during a migration. Incremental and snapshot models only |
| `old_name_view` | How long a [compatibility view](migrations.md#old-names) keeps the old name working after a migration, such as `7d`, or `false` for none. Overrides `[migrations] old_name_views`; valid on every model |

See [Incremental](../incremental.md) for full semantics.

Current compatibility behavior treats an unrecognized `on_schema_change` value as the default `append_new_columns` policy and an unrecognized `replay_on_change` value as `forward`. Use the documented values exactly; future validation may reject unknown values instead of applying these fallbacks.

## Snapshot fields

| Field | Description |
|-------|-------------|
| `unique_key` | Columns identifying one logical record |
| `snapshot_strategy` | `timestamp` or `check` |
| `updated_at` | Source update timestamp for the timestamp strategy |
| `check_columns` | Columns compared by the check strategy, or `[*]` |
| `observed_at` | Observation timestamp for historical inputs |
| `historical_input` | `snapshot` or `changes` |
| `initial_valid_from` | Initial validity policy for first-seen rows |
| `invalidate_hard_deletes` | Close records that disappear from current-state input |
| `valid_from_column` | Override the generated valid-from column name |
| `valid_to_column` | Override the generated valid-to column name |
| `snapshot_full_refresh` | Snapshot full-refresh safety policy |
| `snapshot_schema_change` | Snapshot schema-change policy |

See [Snapshots](../snapshots.md) for strategy combinations, defaults, and safety behavior.

## Custom materialization fields

| Field | Description |
|-------|-------------|
| `config` | Arbitrary values passed to `ctx.config` |
| `placeholders` | Defaults for runtime `@@@placeholder` tokens |

## Diff fields

| Field | Description |
|-------|-------------|
| `row_diff_exclude_columns` | Columns excluded from row-level comparison |
| `row_diff_tolerances` | Numeric comparison tolerances |
| `row_diff_sample_rows` | Deterministic unique-key sample size; `0` disables inherited sampling |
| `row_diff_sample_seed` | Integer seed used for deterministic key hashing |
