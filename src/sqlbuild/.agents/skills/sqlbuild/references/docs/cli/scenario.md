<!-- generated-by: sqlbuild skills -->

# sqb scenario

> Run end-to-end scenario tests against the warehouse or locally with DuckDB.

Online: https://sqlbuild.com/docs/cli/scenario/

## Contents

- sqb scenario test
- sqb scenario capture
- Runtime artifacts

Run end-to-end scenario tests. Scenarios materialize fixture inputs as physical relations, build the real project graph against them, and evaluate expected outputs and assertions. See [Scenarios](../concepts/scenarios.md) for concepts and authoring details.

## sqb scenario test

Run scenario tests against the warehouse.

```bash
sqb scenario test [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select scenarios to run |
| `--exclude` | Exclude scenarios from the selection |
| `--retain` | Keep scenario-owned warehouse artifacts for inspection |
| `--scenario-namespace NAMESPACE` | Isolate warehouse artifacts for this run; overrides environment and config |
| `--local` | Run locally against DuckDB using captured JSONL snapshots |
| `--strict` | Treat missing/stale local snapshots as errors instead of skips |
| `--concurrency N` | Run up to `N` scenarios at once (default: the project `concurrency` setting) |
| `--sync-snapshots` | Capture missing/stale snapshots before local run (requires `--local`) |
| `--refresh` | Recapture all selected snapshots before local run (requires `--local`) |
| `--force` | Bypass snapshot capture safety limits |
| `--max-snapshot-rows` | Override per-relation row limit for capture |
| `--max-snapshot-total-rows` | Override total row limit for capture |
| `--max-snapshot-bytes` | Override per-relation byte limit for capture |
| `--max-snapshot-total-bytes` | Override total byte limit for capture |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `query` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

### Selectors

Scenarios are selected with `--select`. `--exclude` removes scenarios from the selection. Without any selectors, all discovered scenarios run.

| Selector | Example |
|----------|---------|
| Scenario name | `sqb scenario test --select daily_revenue_minimal` |
| Multiple names | `sqb scenario test --select daily_revenue_minimal --select daily_revenue_multi_order` |
| `.sql` file path | `sqb scenario test --select tests/scenarios/revenue/daily_revenue_minimal.sql` |
| Folder | `sqb scenario test --select tests/scenarios/revenue` |
| Scenario-root-relative folder | `sqb scenario test --select revenue` |
| Exclude | `sqb scenario test --select revenue --exclude daily_revenue_multi_order` |

Mixed selector types are supported and the result is de-duplicated by scenario name.

### Remote examples

```bash
# Run all scenarios
sqb scenario test

# Run one scenario
sqb scenario test --select daily_revenue_minimal

# Run and retain warehouse artifacts
sqb scenario test --select daily_revenue_minimal --retain

# Run all scenarios in a folder
sqb scenario test --select revenue
```

### Local examples

```bash
# Run locally (requires prior capture)
sqb scenario test --local

# Run locally, capture missing/stale snapshots first
sqb scenario test --local --sync-snapshots

# Run locally, recapture everything first
sqb scenario test --local --refresh

# Fail on missing/stale snapshots instead of skipping
sqb scenario test --local --strict
```

### Output

Remote scenarios report per-scenario PASS/FAIL with nested check rows:

```
daily_revenue_minimal                                            PASS  0.84s
    expect    expected daily_revenue                             PASS
    expect    assertion no_negative_revenue                      PASS

PASS=1  FAIL=0  TOTAL=1  (0.91s)
```

Each scenario row shows its wall time and the summary shows the total. `--json` reports the same
values as `scenarios[].duration_ms` and `summary.duration_ms`.

Local scenarios add ERROR and SKIP statuses:

```
PASS=2  FAIL=0  ERROR=0  SKIP=1  TOTAL=3  (1.20s)
```

Failed scenarios suggest rerunning with `--retain` for inspection. Local runs always keep the DuckDB file at `target/run/scenarios/<scenario_name>/local.duckdb`.

## sqb scenario capture

Capture scenario input fixtures from the warehouse as JSONL snapshots for local replay.

```bash
sqb scenario capture [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select scenarios to capture |
| `--exclude` | Exclude scenarios from the selection |
| `--retain` | Keep warehouse fixture artifacts after capture |
| `--scenario-namespace NAMESPACE` | Isolate warehouse artifacts for this capture; overrides environment and config |
| `--force` | Bypass snapshot capture safety limits |
| `--max-snapshot-rows` | Override per-relation row limit |
| `--max-snapshot-total-rows` | Override total row limit |
| `--max-snapshot-bytes` | Override per-relation byte limit |
| `--max-snapshot-total-bytes` | Override total byte limit |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `query` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

### Examples

```bash
# Capture all scenarios
sqb scenario capture

# Capture one scenario
sqb scenario capture --select daily_revenue_minimal

# Capture and retain warehouse artifacts
sqb scenario capture --select daily_revenue_minimal --retain
```

Snapshots are written to `tests/_scenario_snapshots/<scenario_name>/` with a `scenario.json` manifest and JSONL files for each fixture relation. These files can be committed to version control.

## Runtime artifacts

Both subcommands report the effective namespace and its source. `scenario test --json` includes
`execution.scenario_namespace` (null when unset) and `execution.scenario_namespace_source`
(`cli`, `env`, `local config`, `project config`, or `unset`). Progress goes to stderr in JSON mode.
See [parallel CI runs](../concepts/scenarios.md#parallel-ci-runs) for namespace configuration and cleanup.

Both remote and local scenario runs write runtime artifacts to `target/run/scenarios/<scenario_name>/`:

```
target/run/scenarios/daily_revenue_minimal/
  cleanup/
    prepare.sql
    final.sql
  fixtures/
    ref__stg_orders.sql
    ref__stg_payments.sql
  models/
    marts/daily_revenue.sql
  expectations/
    expected__daily_revenue.sql
    assertion__no_negative_revenue.sql
```

Local runs additionally write to a `local/` subdirectory and create `local.duckdb`.
