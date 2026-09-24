# Testing: unit tests, scenarios, audits and Rules

| Tool | Checks | Runs against |
|---|---|---|
| SQL unit test (`TEST`) | Model, macro or function logic on mocked inputs | One query; `sqb test`, and before each model in `sqb build` |
| Scenario (`SCENARIO`) | End-to-end logic across a real model graph | Isolated warehouse relations, or local DuckDB replay |
| Audit | Properties of built data (nulls, uniqueness, business rules) | Staging data or each incremental delta, before it is published |
| Rule | Project conventions and SQL quality | Compile time, offline |

## Contents

- Writing a unit test
- Multi-model tests
- Fixtures that fail early
- Repeated cases
- Scenarios
- Audits
- Rules and formatting

## Writing a unit test

Files live under `tests/unit/` (any subfolder). Each file is a `TEST();` header, CTEs, and a
required closing `SELECT 1`.

```sql
-- tests/unit/test_stg_orders.sql
TEST();

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 'completed' AS status,
         CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status,
         CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at
),
__assert__no_null_ids AS (
  SELECT * FROM __ref("stg_orders") WHERE order_id IS NULL
)
SELECT 1
```

| CTE prefix | Meaning |
|---|---|
| `__source__<name>` | Mock `__source("<name>")` |
| `__ref__<name>` | Mock `__ref("<name>")`; that model's real SQL does not run |
| `__seed__<name>` | Mock `__seed("<name>")` |
| `__table_fn__<name>` | Mock a table function invocation |
| `__macro__<name>` | Replace every `@<name>(...)` call |
| `__expected__<model>` | Expected rows of the model's real SQL, compared both ways on the listed columns only |
| `__assert__<name>` | Passes when the query returns zero rows |
| anything else | Helper CTE visible to mocks and model SQL |

An `__expected__<model>` CTE compares only the columns it lists, matched by name, so column order
does not matter and unlisted model columns are ignored. Row counts are always compared. Listing a
column the model does not output is a clear test error. When the expected CTE's columns are not
explicit (for example `SELECT *` from another CTE), SQLBuild compares every column by position.

Macros work inside tests, so reusable mock generators such as `@mock_orders(count=5)` are normal.
Tests can also target a macro, UDF or table function directly; see
[docs/concepts/testing.md](docs/concepts/testing.md) for those modes.

## Multi-model tests

Mock only the sources, give `__expected__` for the model you care about, and every intermediate
model runs from its real SQL. Mock an intermediate with `__ref__<name>` only when you deliberately
want to cut the chain there.

```bash
sqb test --select fact_orders --inspect   # offline: real models executed, mocks, gaps
sqb test --select fact_orders             # run
```

## Fixtures that fail early

With SQL analysis enabled, SQLBuild statically checks fixture shapes before connecting: missing
columns are reported with the test path and the models that read them. SQLBuild never invents
missing fixture values. Cast literal fixture values to the types the model expects
(`CAST('2026-04-01' AS DATE)`), and give every column the model reads.

On failure, reports show unexpected and missing row counts with bounded samples, and the changed
columns when exactly one row differs each way.

## Repeated cases

| Pattern | Result |
|---|---|
| Several `TEST` blocks in one file | One result per block |
| A `VALUES` or macro case table | One aggregate result |
| `parameters (...)` plus named `cases (...)` in the header | One result per named case |

```sql
TEST (
  name "order_status_maps_source_states",
  parameters (source_status string, expected_status string),
  cases (
    completed (source_status "completed", expected_status "completed"),
    cancelled (source_status "cancelled", expected_status "excluded"),
  ),
);
```

## Scenarios

Use scenarios when a single test query becomes unwieldy: coherent customers, orders, payments and
refunds across many models. Files live under `tests/scenarios/` (one scenario per file; the stem
is its unique name), with a `SCENARIO (description "...", tags [...]);` header and the same CTE
conventions.

```bash
sqb scenario test --select daily_revenue_minimal           # build in isolated relations
sqb scenario capture --select daily_revenue_minimal        # snapshot inputs as JSONL
sqb scenario test --local                                  # replay locally in DuckDB
sqb scenario test --local --sync-snapshots                 # capture stale snapshots, then replay
```

Snapshots go to `tests/_scenario_snapshots/<name>/` and can be committed, so CI can run scenarios
without warehouse credentials.

## Audits

Built-ins: `not_null`, `unique`, `accepted_values (values [...])`,
`relationships (to "<model>", field "<column>")`. Attach them in the model's column schema:

```sql
MODEL (
  materialized table,
  columns (
    order_id (audits [not_null, unique]),
    status (audits [accepted_values (values ["placed", "completed", "cancelled"])]),
  ),
);
```

- `error` severity blocks publication (the staging table is not swapped in, or the delta is not
  applied); `warn` reports and continues. Override per audit: `not_null (severity error)`.
- Custom generic audits live in `audits/generic/`; one-off singular audits in `audits/singular/`
  with an `AUDIT (name "...", severity error);` header and a query returning failing rows.
  Singular audits attach to the most downstream model they reference.
- Measurement audits compare metrics with warning and error thresholds.
- `sqb audit --select <models>` runs audits on their own.

## Rules and formatting

Rules are compile-time checks over SQL, models, dependencies, contracts, tests and paths. They run
during `sqb compile` and block artifacts when they fail.

```bash
sqb rules list                    # catalogue
sqb rules show <code>             # what a rule checks and how to fix it
sqb rules run <code-or-family> --select <models>
sqb format --check                # report formatting changes without writing
sqb format --select <models>      # rewrite deterministically
```

Fix the underlying issue rather than suppressing a finding; intentional exceptions are covered in
[docs/concepts/rules/findings-and-exceptions.md](docs/concepts/rules/findings-and-exceptions.md).

Full reference: [docs/concepts/testing.md](docs/concepts/testing.md),
[docs/concepts/scenarios.md](docs/concepts/scenarios.md), [docs/concepts/audits.md](docs/concepts/audits.md),
[docs/concepts/rules.md](docs/concepts/rules.md), [docs/cli/test.md](docs/cli/test.md).
