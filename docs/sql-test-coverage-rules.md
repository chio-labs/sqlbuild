# SQL test coverage rules

`SQBRTEST202` (`minimum-tests`) requires each non-passthrough model to have at least
`min_tests_per_model` model-mode SQL unit tests. `SQBRTEST203` (`empty-input-only-test`) rejects
tests that cannot fail because they only prove that empty inputs produce no rows. Both rules are
enabled by default when the `SQBRTEST` family is selected.

## Empty-input-only tests

Do not write tests like this one:

```sql
TEST (name "orders__empty_inputs_produce_no_rows");

WITH __source__raw_orders AS (
  SELECT NULL AS order_id, NULL AS amount
  WHERE FALSE
), __assert__empty_inputs_produce_no_rows AS (
  SELECT 1 AS unexpected_row
  FROM __ref("orders")
)
SELECT 1
```

When a model's rows come only from its inputs, this test passes for almost any model logic, so it
adds no coverage. `SQBRTEST203` flags a model-mode test when all of the following hold:

- Every mock (`__ref__`, `__source__`, `__seed__`, `__dbt_ref__`, `__table_fn__`) is a single
  `SELECT` without a set operator that is filtered by `WHERE FALSE` or `WHERE 1 = 0`, limited by
  `LIMIT 0`, or is `SELECT * FROM __EMPTY_FIXTURE()`. A `UNION` whose last branch is filtered is
  not empty.
- Every `__expected__<model>` CTE is empty in the same way, or there is none.
- Every `__assert__` CTE is a bare row-existence check, `SELECT <anything> FROM __ref("<model>")`
  on a tested model, with no `WHERE`, `JOIN`, `GROUP BY`, `HAVING`, `QUALIFY`, set operator,
  `EXISTS`, or subquery.
- The test has no `__macro__` mocks.

Macro, UDF, and table-function tests are never flagged, and SQL that the rules parser cannot read
is never flagged.

Replace a flagged test with one that mocks representative rows and asserts concrete transformed
output, or delete it.

## Legitimate empty-input tests

An empty-input test is legitimate when it asserts concrete output. For example, a global aggregate
must still return one zero-valued summary row when it has no input:

```sql
TEST (name "order_summary__empty_inputs_return_zero_row");

WITH __source__raw_orders AS (
  SELECT CAST(NULL AS INTEGER) AS order_id, CAST(NULL AS INTEGER) AS amount
  WHERE FALSE
), __expected__order_summary AS (
  SELECT 0 AS order_count, 0 AS total_amount
)
SELECT 1
```

An `__assert__` that compares the model against a summary row with `EXCEPT` in both directions,
or one that filters for invalid rows, is also not flagged.

## Reviewed exceptions

List deliberate exceptions by test name in the project file, not in the test:

```toml
[rules.rule_options.SQBRTEST203]
allowed_tests = ["customers__empty_inputs_produce_no_rows"]
```

`allowed_tests` must be a list of strings. For a parameterized test, an entry may name the whole
test or one expanded case. An entry that names no existing test is reported as stale.

## Interaction with minimum tests

Tests matched by `SQBRTEST203` do not count toward `min_tests_per_model`, whether or not
`SQBRTEST203` is selected, so filler cannot satisfy the minimum. Tests listed in `allowed_tests` are
reviewed exceptions and do count. A `SQBRTEST202` finding reports how many empty-input-only tests
it did not count.
