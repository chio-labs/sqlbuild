<!-- generated-by: sqlbuild skills -->

# Cascade propagation

> How a change signal propagates downstream through the DAG, and how each materialization type responds.

Online: https://docs.sqlbuild.com/concepts/planning/cascade-propagation

When a model or function changes, the change signal propagates downstream through the DAG. Every model downstream of a changed node is marked `Upstream changed` in the plan, even if its own SQL and config are identical.

The cascade walk is topological: it processes models in dependency order, so each model sees the resolved state of all its upstreams before deciding its own effective action.

## What cascades

- A query, config, or schema change on any model cascades to all its downstream dependents.
- A function change cascades to every model that calls it (directly or transitively).
- Source freshness changes propagate downstream the same way. See [Source freshness](source-freshness.md).

## How materialization types respond

- **Views** are recreated on every build regardless, so a cascade has no extra cost.
- **Tables** are fully rebuilt, same as if they had changed themselves.
- **Incremental models** receive a replay window from the cascade. A `full` replay always cascades. A `bounded` replay only cascades when the upstream and downstream models share the same `cursor_type` (e.g. both use `timestamp`), so unrelated cursor types don't inherit bounded windows that don't apply. The downstream model's own `replay_on_change` policy takes precedence over any cascaded signal.

## Resolution when multiple upstreams are stale

If a model has multiple stale upstreams with different replay actions, the most aggressive action wins. `full` beats `bounded`, and among bounded actions, the longer duration wins. Ties are broken alphabetically by model name for determinism.

## Overriding cascaded replay

Downstream incremental models can set their own `replay_on_change` policy to override the cascaded signal. If a downstream model declares its own policy, that policy applies instead of the upstream's. If it has no policy, it inherits the upstream's replay scope.

## Replay on change

When a change is detected on an incremental model, `replay_on_change` controls how much data to reprocess:

- **`forward`** (default) - run the normal incremental delta from the cursor. No reprocessing.
- **`bounded-<duration>`** (e.g. `bounded-14d`) - replay the specified window of data.
- **`full`** - drop and rebuild the entire table.

See [Incremental Models: Replay on change](../incremental.md#replay-on-change) for configuration details.
