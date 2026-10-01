<!-- generated-by: sqlbuild skills -->

# Source freshness

> Observe external source changes and propagate them through planning.

Online: https://sqlbuild.com/docs/concepts/planning/source-freshness/

Source freshness lets SQLBuild observe whether external source data changed between runs. A changed
observation propagates through the dependency graph, so plans can explain which downstream models
are affected and choose the correct incremental action.

## Configuration

Source freshness is configured per source in `sources/*.yml` with a `freshness:` block. See [Sources: Source freshness](../sources.md#source-freshness) for the full configuration reference.

## How observations work

During planning, SQLBuild observes the current data version of each source that has freshness configured (or that the adapter can observe automatically):

1. **Observe** - query the source's current data version using the configured strategy.
2. **Compare** - compare the observed version against the last recorded observation from `_sqlbuild_source_freshness` in the target schema.
3. **Propagate** - walk the DAG downstream from changed or unknown sources to identify which models are affected.

Sources without explicit `freshness:` config are auto-observed using the `adapter` strategy if the adapter supports table metadata and the source has a physical table (not an expression source, not a managed source).

Adapter metadata for all sources is fetched in one batched lookup, but each source gets its own
result. When one source can't be observed, only that source is unknown; the others keep their
freshness. The `Freshness metadata` progress line reports the outcome, for example
`Freshness metadata  OK (257 sources, 3 unknown)`. The plan adds one warning per reason, listing up
to 10 sources, such as `source freshness unknown (unavailable) for raw_events, raw_sessions: ...`.
Sources without freshness configuration that the adapter can't observe are not warned about.
Every unknown source is listed with its reason and message under `unknown_source_details` in the
`direct_source_freshness` metadata of `sqb plan --json`; run `sqb freshness` for the same detail
in text form.

## Missing source tables

A source table that a selected model reads must exist before anything runs. If it doesn't,
planning fails with `S405`, naming each missing source, its table, and the selected models that
read it, and pointing at the source declaration:

```
error[S405]: cannot build selected scope: 1 source table read by selected resources does not exist in the warehouse:
  - source 'raw_payments' (raw.payments), read by payments
  = help: create or load the table, correct its database, schema, or table in the source declaration, or stop reading it from the selected models; declared 'raw_payments' at sources/raw.yml:16
```

Create the table, fix the declaration, or leave the reading models out of the selection. Managed
sources and sources with a loader are exempt, because SQLBuild creates their tables when it loads
them. Expression sources, sources without a schema, and wildcard tables are also exempt. A missing
table that only unselected models read does not fail the plan; its freshness is reported as unknown.

The check first looks for each source in the warehouse listing that planning already reads for
source columns, so it normally issues no extra queries. A source the listing does not find (for
example because of identifier case, a stream, a materialized view, or a table in another database)
is then probed directly with `SELECT 1 FROM <relation> WHERE 1=0`, using the same relation name the
model SQL reads. Probes for several such sources run concurrently, within the same limit as other
warehouse inspection reads. Only a not-found error from that probe counts as missing, including a
missing schema, catalog, or attached database; any other error (for example a connection error)
fails planning with that error. On Snowflake the probe may need a running warehouse, but it only
runs for sources the listing did not find.

Snowflake reports a missing table and a table the current role can't read with the same error, and
its listing hides tables the role can't access. For those sources `S405` says the table "does not
exist or is not readable by" the role, names the role in use when the connection reports it, and the help suggests both fixes:
create or load the table, or grant `SELECT` on it to that role.

A table that a model's own `pre_hook` creates does not exist yet when the plan is made, so planning
fails with `S405`. Declare such a table as a managed source or a source with a loader, or create it
before planning.

## Lag tolerance

For timestamp-based freshness, `lag_tolerance` controls how much the observed value can drift before being considered a real change. If the current timestamp is within the tolerance of the previous observation, the source is treated as unchanged. This is useful for sources where the freshness timestamp moves by seconds or minutes on every query but the underlying data hasn't meaningfully changed.

## State storage

Source freshness observations are appended to `_sqlbuild_source_freshness` in each target schema.
Failed work does not replace the prior successful observation, so the next plan still
sees the pending source change.

Direct observations are resolved across all target schemas in the project, so a source referenced by
models in different schemas is tracked consistently.

Use [`sqb freshness`](../../cli/freshness.md) to observe source freshness on demand without triggering a build.
