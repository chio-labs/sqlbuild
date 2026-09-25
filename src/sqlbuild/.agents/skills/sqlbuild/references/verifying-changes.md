# Verifying changes with sqb diff

A model that compiles, builds and passes tests can still return the wrong numbers. `sqb diff`
proves what changed. It has two modes:

- **Model diff** compares built models between two targets.
- **Query diff** compares any two SQL queries on one connection. No build is required.

## Contents

- Choosing a mode
- Model diff
- Query diff
- Reading results
- Common failures

## Choosing a mode

| Situation | Use |
|---|---|
| You rebuilt models in a dev target and want to compare them with prod | Model diff `prod:dev` |
| You changed logic and want to see the effect before building anything | Query diff: current query vs proposed query |
| You fixed a bug and want to show exactly which rows changed | Query diff with `--key` and labels |
| Two tables or systems should agree (migration, reconciliation) | Query diff with `--key`, `--tolerance`, `--exclude-column` |
| You only care whether columns or types changed | Model diff `--schema-only` |

## Model diff

```bash
sqb diff <FROM>:<TO> (--full | --schema-only | --bounded <window>) --select <selector> [flags]
```

- `FROM` and `TO` are configured target names. The
  `TO` target's connection runs the comparison and must be able to read both namespaces.
- `--select` is required. Exactly one mode is required.
- `--full` and `--bounded` join rows on the model's `unique_key`; models without one support only
  `--schema-only`.
- `--bounded 14d` compares a recent cursor window (integer cursors take an integer). A model
  without a cursor falls back to a full comparison.

Typical dev-versus-prod check after changing a model:

```bash
sqb build --select fact_orders --target dev --defer-to prod
sqb diff prod:dev --full --select fact_orders
```

Large models:

- Deterministic key sampling caps the wide comparison: `--sample-rows 50000 --sample-seed 7`,
  or the `row_diff_sample_rows` setting. `--exhaustive` disables sampling for one run. A sampled
  pass means "no differences in the sampled keys", never full equality.
- `--max-models` and `--max-columns` fail loudly instead of truncating a broad selector.

Model-level settings in the `MODEL()` header:

```sql
MODEL (
  materialized table,
  unique_key [order_id],
  row_diff_exclude_columns [loaded_at],
  row_diff_tolerances (
    by_column (
      total_revenue_cents (absolute 1),
    ),
  ),
);
```

## Query diff

```bash
sqb diff \
  --left-query "<sql>" | --left-query-file <path> \
  --right-query "<sql>" | --right-query-file <path> \
  (--key <column> [--key <column> ...] | --unkeyed) \
  [--left-label <name>] [--right-label <name>] \
  [--exclude-column <column>] [--tolerance <column>:absolute=<n> | <column>:relative=<n>] \
  [--target <target>] [--json] [--verbose]
```

Rules that matter:

- Give `--key` for the row identity (repeat for composite keys), or `--unkeyed` to compare exact
  full-row multisets. One of them is required.
- Queries are raw warehouse SQL on the active target (or `--target`). `__ref()`, `__source()` and
  macros are not expanded, so use physical names. Get them from `qualified_name` in
  `sqb plan --json` or `sqb lineage <model> --format json`.
- Both sides must produce the same column names and types. A type difference makes the result
  `incomplete`. Cast both sides to a common type, for example `amount::DOUBLE`.
- SQLBuild materializes both queries as short-lived tables, compares them, and removes them.
- Labels make the report readable: `--left-label current --right-label proposed`.

Recipes:

```bash
# Effect of a logic change before building: current model output vs proposed SQL
sqb diff \
  --left-query "SELECT * FROM analytics.fact_orders" \
  --right-query-file /tmp/proposed_fact_orders.sql \
  --key order_id --left-label current --right-label proposed

# Reconcile two tables, ignoring a load timestamp and float noise
sqb diff \
  --left-query "SELECT order_id, total::DOUBLE AS total, loaded_at FROM legacy.orders" \
  --right-query "SELECT order_id, total::DOUBLE AS total, loaded_at FROM analytics.orders" \
  --key order_id --exclude-column loaded_at --tolerance total:absolute=0.01

# No natural key: compare full rows
sqb diff --left-query "SELECT status FROM a" --right-query "SELECT status FROM b" --unkeyed
```

## Reading results

- Exit code `0`: no differences. `1`: differences found. `2`: incomplete comparison or error.
- The summary shows schema differences, row counts per side, then equal, unequal, left-only and
  right-only rows, followed by changed columns with match percentages and example values.
- `--verbose` shows more examples. `--json` (query diff) prints structured output to stdout.
  `--json-output <path>` writes structured output while keeping the terminal summary.
- Report findings to the user as evidence: which keys changed, which columns, and why that is or
  is not expected.

## Common failures

| Message | Fix |
|---|---|
| `raw-query diff requires one or more --key values or explicit --unkeyed` | Add `--key` or `--unkeyed` |
| `model diff requires FROM:TO` | Give `prod:dev`, or use `--left-query`/`--right-query` |
| Outcome `incomplete` with schema differences | Align column names and cast types on both sides |
| `Table Function with name __ref does not exist` | Replace `__ref()` with the physical relation name |
| Full/bounded diff rejected without `unique_key` | Add `unique_key` to the model or use `--schema-only` |

Full reference: [docs/cli/diff.md](docs/cli/diff.md) and [docs/concepts/diff.md](docs/concepts/diff.md).
