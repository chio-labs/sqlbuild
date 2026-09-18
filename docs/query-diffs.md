# Query and model data diffs

`sqb diff` compares either selected models or two literal read-only SQL queries. Both input modes
use the same schema inspection, row-count reporting, key validation, deterministic sampling,
numeric tolerance, excluded-column, evidence, JSON, and exit-code behavior.

## Compare models

Model mode keeps the `FROM:TO` range and selectors:

```bash
sqb diff prod:dev --full --select orders
```

By default, row identity comes from each model's `unique_key`. Repeated `--key` arguments override
that configuration for one invocation:

```bash
sqb diff prod:dev --full --select order_lines \
  --key order_id \
  --key line_id
```

For a model without a stable row key, opt in to exact full-row multiset comparison with
`--unkeyed`. Duplicate rows retain their multiplicity; SQLBuild never guesses a key.

```bash
sqb diff prod:dev --full --select daily_order_totals --unkeyed
```

## Compare raw queries

Query mode omits `FROM:TO` because each query identifies its own input. Supply each side inline or
from a UTF-8 file, and choose keyed or unkeyed comparison explicitly:

```bash
sqb diff \
  --left-query 'SELECT order_id, amount_cents FROM analytics.orders_before' \
  --right-query 'SELECT order_id, amount_cents FROM analytics.orders_after' \
  --key order_id
```

```bash
sqb diff \
  --left-query-file queries/orders_before.sql \
  --right-query-file queries/orders_after.sql \
  --key account_id \
  --key order_id
```

Raw inputs must contain exactly one read-only `SELECT`, `WITH`, or `VALUES` expression. SQLBuild
does not expand `ref()` or other SQLBuild templates in these inputs. The active target connection
executes both sides; use `--target NAME` to select another configured connection.

Query mode performs a full comparison when no comparison mode flag is present. `--schema-only` is
also available. `--bounded` is model-specific; filter both raw queries directly when a bounded
query comparison is needed.

### Sampling, tolerances, and exclusions

Keyed query comparisons support deterministic union-key sampling and the same bounded mismatch
examples as model comparisons:

```bash
sqb diff \
  --left-query-file queries/orders_before.sql \
  --right-query-file queries/orders_after.sql \
  --key order_id \
  --sample-rows 50000 \
  --sample-seed 7
```

Use repeated invocation overrides where needed:

```bash
sqb diff \
  --left-query-file queries/orders_before.sql \
  --right-query-file queries/orders_after.sql \
  --key order_id \
  --exclude-column loaded_at \
  --tolerance amount_cents:absolute=1 \
  --tolerance conversion_rate:relative=0.001
```

`--exhaustive` disables inherited or requested sampling. Unkeyed comparison is always exhaustive
and exact, so it does not accept sampling or numeric tolerances.

## Stable query results and cleanup

SQLBuild materializes each raw query once in the selected target's default schema before comparing
it. Artifacts use a reserved run-owned name and are dropped immediately when the command finishes,
including after comparison errors.

Each successfully created artifact publishes an immutable `query_diff_artifact` fingerprint. The
fingerprint is ownership evidence for crash recovery only: running and comparing the queries never
reads historical fingerprints, and fingerprints do not represent planned, running, complete, or
cleaned workflow states.

If a process stops before immediate cleanup, the next query diff and `sqb janitor` can remove an
expired artifact only when its exact physical identity and reserved name match its ownership
fingerprint. A matching name without ownership evidence is reported for manual investigation and
is not deleted automatically.

The recovery TTL defaults to 24 hours and accepts SQLBuild fixed-duration syntax:

```toml
[diff]
query_artifact_ttl = "24h"
```

The TTL is a crash-recovery backstop, not the normal cleanup path. Historical ownership inspection
problems are reported but do not prevent the current queries from running. Failure to publish
ownership for a newly created artifact, or failure to remove a current-run artifact, is an execution
error.

## Structured output and exit behavior

Use `--json-output PATH` in either mode. Query results include `input_kind = "query"`; model results
use `input_kind = "model"`. Exit code `0` means no differences were found. Exit code `1` means
differences were found or the comparison could not execute successfully.
