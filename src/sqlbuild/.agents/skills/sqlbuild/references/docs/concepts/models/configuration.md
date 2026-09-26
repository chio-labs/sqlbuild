<!-- generated-by: sqlbuild skills -->

# Configuration

> MODEL() header fields and SQL-analysis controls.

Online: https://docs.sqlbuild.com/concepts/models/configuration

## Contents

- Common fields
- SQL analysis
- Table fields
- Incremental fields
- Snapshot fields
- Custom materialization fields
- Diff fields

## Common fields

| Field | Description |
|-------|-------------|
| `materialized` | `view`, `table`, `incremental`, `snapshot`, or a custom materialization name |
| `tags` | Tags used by selectors |
| `description` | Human-readable model description |
| `columns` | Model-local column declarations or inherited-column audit augmentation |
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

## SQL analysis

SQL analysis has project, invocation, and model gates:

1. `settings.sql_analysis` must be enabled.
2. `--no-sql-analysis` must not be present.
3. `MODEL (sql_analysis false)` can disable analysis for that model. If omitted, the project setting
   is used.

A model cannot re-enable analysis when either broader gate disables it. The older `sql_validation`
and `--no-sql-validation` spellings remain compatibility aliases; use `sql_analysis` for new
configuration.

## Table fields

| Field | Description |
|-------|-------------|
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
| `cursor_inputs` | Upstream names mapped to cursor columns |
| `unique_key` | Merge or delete/insert matching columns |
| `incremental_mode` | Set to `microbatch` for batched execution |
| `microbatch_strategy` | Required in microbatch mode: `watermark` or `rolling_window` |
| `cursor_watermark_mode` | Watermark strategy policy: `all` or `any` |
| `batch_size` | Timestamp duration string such as `1d` or `1h`; use a numeric string such as `"1000"` for an integer cursor |
| `batch_concurrency` | Concurrent batch workers; values above `1` require `delete_insert` and the project concurrency gate |
| `microbatch_limit` | Nested `max_batches` and `action` policy for watermark execution |
| `lookback` | Backward replay extension |
| `append_cursor_inclusive` | Include (`true`, default) or exclude (`false`) the current append-cursor boundary |
| `merge_exclude_columns` | Columns left unchanged by matched-row merge updates |
| `full_refresh` | Optional model execution override: `false` always runs incrementally, `true` always full-refreshes, and omission follows the command |
| `on_schema_change` | `append_new_columns`, `sync_all_columns`, `ignore`, or `fail` |
| `replay_on_change` | `forward`, `full`, or `bounded-<duration>` |
| `migrate_from` | Old model name (or `schema.name`) whose data this model takes over; see [Model migrations](migrations.md). Also valid on snapshot models |
| `migrate_force` | `true` replaces a destination that already has its own build history during a migration |

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
