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

## Lag tolerance

For timestamp-based freshness, `lag_tolerance` controls how much the observed value can drift before being considered a real change. If the current timestamp is within the tolerance of the previous observation, the source is treated as unchanged. This is useful for sources where the freshness timestamp moves by seconds or minutes on every query but the underlying data hasn't meaningfully changed.

## State storage

Source freshness observations are appended to `_sqlbuild_source_freshness` in each target schema.
Failed work does not replace the prior successful observation, so the next plan still
sees the pending source change.

Direct observations are resolved across all target schemas in the project, so a source referenced by
models in different schemas is tracked consistently.

Use [`sqb freshness`](../../cli/freshness.md) to observe source freshness on demand without triggering a build.
