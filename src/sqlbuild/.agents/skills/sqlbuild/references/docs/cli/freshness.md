<!-- generated-by: sqlbuild skills -->

# freshness

> Observe source freshness without writing state.

Online: https://docs.sqlbuild.com/cli/freshness

## Contents

- Usage
- Flags
- Source selection
- Observation without state
- Comparing against state
- CI integration
- JSON output
- See also

# sqb freshness

Observes the current data version of each source and reports whether the data has changed since the last build. Does not write any state or trigger builds.

## Usage

```bash
sqb --project-dir <path> freshness [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--state` | Compare observations against stored freshness state from the last build |
| `--fail-on-error` | Exit with code 1 if any source observation fails or is unknown |
| `--fail-on-stale` | Exit with code 1 if any source has changed, is unknown, or errored (requires `--state`) |
| `--json` | Output as JSON instead of human-readable text |
| `--json-output` | Write JSON output to a file path (also prints text to stdout unless `--json` is set) |
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `--select`, `-s` | Select specific sources or models (sources upstream of selected models are included) |
| `--exclude` | Exclude specific sources or models |

## Source selection

Without `--select`, all sources in the project are observed. When `--select` is provided, selectors work like other commands: you can select sources by name, or select models and their upstream sources are automatically included:

```bash
# Observe all sources
sqb freshness

# Observe a specific source
sqb freshness --select raw_orders

# Observe sources upstream of a model
sqb freshness --select fact_orders
```

## Observation without state

By default, `sqb freshness` observes the current data version of each source and reports what it found. No comparison is made against previous observations:

```bash
sqb freshness
```

```
Source freshness

Observed (3)
  raw_customers  timestamp  2026-06-05T14:30:00  adapter
  raw_orders     timestamp  2026-06-05T15:45:00  column  tolerance 15m
  raw_payments   integer    42871                 column

Summary: observed=3 changed=0 unchanged=0 tolerated=0 unknown=0 errors=0
```

Sources without explicit `freshness:` config are auto-observed using the `adapter` strategy if the adapter supports table metadata. Sources that can't be observed (expression sources, managed sources without freshness config on unsupported adapters) show as `unknown`.

## Comparing against state

Use `--state` to compare current observations against the freshness state stored from the last successful build:

```bash
sqb freshness --state
```

```
Source freshness

Changed (1)
  raw_orders     previous 2026-06-05T12:00:00  current 2026-06-05T15:45:00  tolerance 15m

Unchanged (1)
  raw_customers  previous 2026-06-05T14:30:00  current 2026-06-05T14:30:00

Tolerated (1)
  raw_payments   previous 2026-06-05T14:28:00  current 2026-06-05T14:30:00  tolerance 15m

Summary: observed=0 changed=1 unchanged=1 tolerated=1 unknown=0 errors=0
```

### Statuses

| Status | Meaning |
|--------|---------|
| `observed` | Successfully observed (no state comparison) |
| `changed` | Data version differs from the stored state |
| `unchanged` | Data version matches the stored state exactly |
| `tolerated` | Data version differs but is within the `lag_tolerance` threshold |
| `unknown` | No freshness config and adapter metadata unavailable, or no previous state to compare against |
| `error` | Observation failed (e.g. source table does not exist, query error) |

## CI integration

Use `--fail-on-error` to fail the pipeline if any source can't be observed:

```bash
sqb freshness --fail-on-error
```

Use `--fail-on-stale` with `--state` to fail if any source has new data that hasn't been built yet:

```bash
sqb freshness --state --fail-on-stale
```

This is useful for CI gates that should block if source data has changed but the pipeline hasn't run yet.

## JSON output

```bash
sqb freshness --json
```

```json
{
  "sources": [
    {
      "name": "raw_orders",
      "status": "observed",
      "strategy": "column",
      "value_kind": "timestamp",
      "current_data_version": "2026-06-05T15:45:00",
      "previous_data_version": null,
      "lag_tolerance": "15m",
      "target": {
        "database": null,
        "schema": "raw",
        "name": "orders"
      },
      "message": null
    }
  ],
  "summary": {
    "observed": 1,
    "changed": 0,
    "unchanged": 0,
    "tolerated": 0,
    "unknown": 0,
    "errors": 0
  }
}
```

## See also

- [Sources: Source freshness](../concepts/sources.md#source-freshness) for freshness configuration
- [Planning and Change Detection](../concepts/planning.md) for how freshness feeds into change-aware builds
