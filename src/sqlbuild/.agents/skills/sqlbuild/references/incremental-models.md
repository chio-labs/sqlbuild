# Incremental and microbatch models

SQLBuild incremental models are cursor-driven. SQLBuild reads the target's current cursor maximum
and the listed inputs' extents, computes the replay window, filters inputs to it, and applies DML.
There is no separate checkpoint to manage in the default sequential path.

## Contents

- Strategies
- Cursors and the automatic input filter
- Microbatch execution
- Watermark roles and limits
- Replay, full refresh and schema changes
- Workflow and checks

## Strategies

| Strategy | Needs | Behaviour |
|---|---|---|
| `append` | optional cursor | Inserts new rows. `append_cursor_inclusive true` (default) uses `>=` at the boundary |
| `delete_insert` | `cursor` or `unique_key` | Deletes the target rows in the window (or matching keys), inserts the delta |
| `merge` | `unique_key` | Upserts by key; the cursor limits which upstream rows are scanned |

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  cursor_inputs (
    fact_orders ordered_at,
  ),
);

SELECT customer_id, ordered_at AS activity_hour, line_total_cents
FROM __ref("fact_orders")
```

## Cursors and the automatic input filter

| Field | Meaning |
|---|---|
| `cursor` | Output column tracking position |
| `cursor_type` | `timestamp` or `integer` |
| `cursor_grain` | `second`, `minute`, `hour`, `day`, `month`, `year` (timestamp cursors) |
| `cursor_start` | Floor; never replay before this value |
| `cursor_inputs` | Upstream ref/source names and their cursor columns; required with multiple inputs |
| `lookback` | Extend the window start backwards, for example `lookback 3d`, for late data |

Behaviour to rely on:

- **Listed inputs are filtered for you.** SQLBuild wraps each input listed in `cursor_inputs` in
  `WHERE <cursor> >= start AND <cursor> < end`. Do not add the same filter by hand.
- **Unlisted inputs are read in full** and do not bound the window. Leave dimension and lookup
  tables unlisted; list every input whose new data should drive reprocessing.
- With several listed inputs, the window end is the minimum of their maxima, so a fast input
  cannot run ahead of a slow one.
- `__cursor_start()` (inclusive) and `__cursor_end()` (exclusive) expose the effective bounds when
  SQL needs them explicitly, for example to filter an unlisted input or compute a derived range.
  They are valid only in cursor incremental model SQL, not in test, hook, audit or function SQL.
  SQL unit tests of such a model render them with a wide default window, or the window declared
  with `cursor_start`/`cursor_end` in the `TEST(...)` header; see
  [testing.md](testing.md#cursor-windows-in-tests).
- For `delete_insert` and `merge`, only target rows whose cursor falls inside the window are
  rewritten. A change in an unlisted input does not rewrite older rows.

## Microbatch execution

`incremental_mode microbatch` splits the window into batches. Each batch creates its delta, runs
delta audits, applies DML and cleans up. Choose the strategy explicitly:

| `microbatch_strategy` | Window source |
|---|---|
| `watermark` | Declared input availability (timestamp or integer cursors) |
| `rolling_window` | A timestamp window relative to the current run |

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  incremental_mode microbatch,
  microbatch_strategy watermark,
  cursor_watermark_mode all,
  cursor_inputs (
    fact_orders (column ordered_at, roles [filter, watermark]),
  ),
  batch_size 1d,
);
```

- `batch_size` is a duration (`1d`, `6h`, `1mo`) or an integer for integer cursors.
- Sequential batches are the default and use no state table. Concurrent batches are opt-in:
  `[settings] microbatch_concurrency = true` in the project plus `batch_concurrency N` on the
  model (`delete_insert` only). Raise concurrency deliberately; each batch uses warehouse compute.
- Mixed grains align automatically: an hourly model downstream of a daily one processes whole
  days.

## Watermark roles and limits

Each watermark `cursor_inputs` entry declares `roles`:

- `filter`: SQLBuild filters that input's rows to each batch window.
- `watermark`: the input's maximum contributes availability. A watermark-only input is not
  filtered.
- `cursor_watermark_mode all` waits for the slowest watermark input; `any` lets any one advance.

Batch limits protect ordinary runs from huge ranges:

```sql
microbatch_limit (
  max_batches 7,
  action cap_from_end,
),
```

| `action` | When the range exceeds `max_batches` |
|---|---|
| `error` | Fail before hooks or mutation |
| `warn` | Warn and run the full range |
| `cap_from_start` | Run the oldest N batches, defer the rest |
| `cap_from_end` | Run the newest N batches, defer older work |

Project-wide `[microbatches.limits]` supports only `error` and `warn`. `--max-microbatches N` on
plan or build is a one-run hard ceiling and explicit authorization for an intentional backfill.

## Replay, full refresh and schema changes

- `replay_on_change` decides how much to reprocess when the model's identity changes:
  `forward` (default), `full`, or `bounded-<duration>` such as `bounded-14d`.
- `--full-refresh` rebuilds selected models unless a model sets `full_refresh false`;
  `full_refresh true` always rebuilds.
- `on_schema_change`: `append_new_columns` (default), `sync_all_columns`, `ignore`, `fail`.
- Cursor overrides for one run: `--start-cursor-ts/--end-cursor-ts` (ISO) or
  `--start-cursor-int/--end-cursor-int`.

## Workflow and checks

1. `sqb compile --select <model>`.
2. `sqb plan --select <model>` and read the action, reason, cursor bounds and backfill range.
3. `sqb build --select <model>`.
4. Verify with `sqb diff prod:dev --bounded 14d --select <model>` or a query diff over the window.

Full reference: [docs/concepts/incremental.md](docs/concepts/incremental.md),
[docs/concepts/planning/cascade-propagation.md](docs/concepts/planning/cascade-propagation.md),
[docs/concepts/snapshots.md](docs/concepts/snapshots.md).
