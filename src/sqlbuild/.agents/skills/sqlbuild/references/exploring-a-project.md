# Exploring a project

Use SQLBuild's own introspection instead of grepping and guessing. `scope`, `lineage`, `dag`,
`compile` and `test --inspect` are offline; `query`, `plan` and `diff` read the warehouse.

## Contents

- Declaration scope: sqb scope
- Model and column lineage: sqb lineage
- Graph and plan as data
- Looking at data: sqb query
- Test boundaries: sqb test --inspect

## Declaration scope: sqb scope

Macros, enums and constants are visible by folder. `sqb scope` answers, for any resource: what can
it see, what does it actually use, where did each declaration come from, and what would break if
it moved. It is read-only and offline.

Targets are kind-qualified; bare names are rejected:

```bash
sqb scope model:stg_orders
sqb scope test:stg_orders__excludes_cancelled
sqb scope macro:normalize_order_status
sqb scope enum:order_status
sqb scope constant:minimum_order_value
sqb scope models/staging/orders/stg_orders.sql
```

Model-private declarations include the owner: `enum:model:stg_orders._state`.

Common questions:

| Question | Command |
|---|---|
| What does this model use, including declarations those use? | `sqb scope model:orders --used-only --dependency-depth 1` |
| Why is this macro visible or not visible here, and where should it live? | `sqb scope model:orders --explain macro:formatted_order_total` |
| Which declarations are close by but unavailable? | `sqb scope model:orders --include-nearby` |
| What could a new file at this path use? | `sqb scope --at models/commerce/new_model.sql` |
| Would moving this model break visibility? | `sqb scope model:orders --as-path models/finance/orders.sql` |
| Which folders hold declarations, and what is in one? | `sqb scope model:orders --browse models`, then `sqb scope model:orders --list models/commerce` |
| Only macros matching a pattern | `sqb scope model:orders --kind macro --match "format_*"` |

Report sections: **Used**, **Scope chain** (owner folder, parents, project globals), **Available**
(globals collapsed; `--globals all` expands them), **Relationship grants** (tests and scenarios),
**Nearby unavailable**, **Diagnostics**. Use `--json` for machine-readable output.

Placement rules the scope report reflects:

| Location | Visible to |
|---|---|
| Top-level `macros/`, `enums/`, `constants/` | The whole project |
| `<folder>/_sqlbuild/macros/` (or `enums/`, `constants/`) | That folder and everything below |
| `<folder>/_sqlbuild/_macros/` (or `_enums/`, `_constants/`) | Files directly in that folder only |
| Underscored `_name` constant or enum inside `MODEL()` | That model only |

A declaration must sit in the narrowest folder containing all of its consumers; a project-wide
declaration used by only one folder tree is rejected at compile. `--explain` shows the narrowest
required placement.

## Model and column lineage: sqb lineage

```bash
sqb lineage fact_orders                         # upstream tree (default)
sqb lineage fact_orders --direction both        # upstream and downstream
sqb lineage fact_orders --direction downstream --depth 1
sqb lineage --select tag:finance --format list  # edges for a selection
sqb lineage fact_orders dim_customers --depth 1 --format list   # direct parents of several models
sqb lineage --select tag:finance --direction upstream --depth 1  # expand a selection
sqb lineage fact_orders.total_cents             # where a column comes from
sqb lineage fact_orders.order_id --direction downstream   # who consumes a column
```

- Targets are resources (models, sources, seeds, functions), optionally with the printed kind
  prefix (`model:fact_orders`). `model.column` switches to column lineage (one column per call).
- Graph operators such as `1+fact_orders` are not lineage targets: use `--direction` and
  `--depth`. Without `--direction`, `--select` shows only edges inside the selection.
- Formats: `tree` (default), `list` (edges), `json` (nodes, edges, `qualified_name`).
- Column edges carry a transform type (`direct`, `expression`, `aggregation`, `cast`, `star`,
  `constant`) and a confidence level. `--mode fast` trades detail for speed on large projects.
- Before renaming, retyping or dropping a column, run a downstream column trace and update or
  warn about every consumer.

## Graph and plan as data

- `sqb dag --json`: every node, edge and check. Good for scripting over the whole project.
- `sqb compile --json`: diagnostics, contract results and per-model lineage summaries.
  `--select` focuses analysis while keeping whole-project reference checks.
- `sqb plan --json --select <models>`: per model the action, reason, incremental strategy,
  cursor bounds, backfill and `qualified_name` (the physical relation).

Plan reasons: first run, query changed, config changed, schema changed, function changed, upstream
changed, run despite unchanged. Direct mode still builds the whole selected scope; the reasons
explain it.

## Looking at data: sqb query

```bash
sqb query "SELECT status, COUNT(*) FROM analytics.orders GROUP BY 1" --format table
sqb query --file /tmp/check.sql --limit 100
```

Runs raw SQL on the active target (physical names). Formats: `long` (default), `table`, `json`,
`csv`. Default limit 20; `--no-limit` removes it. Profile inputs before writing joins and check
outputs after building.

## Test boundaries: sqb test --inspect

`sqb test --select fact_orders --inspect` lists mocked sources and refs, the real models a test
will execute in order, expected models and unsatisfied dependencies, without a warehouse. Use it
before writing or debugging a multi-model test.

Full reference: [docs/cli/scope.md](docs/cli/scope.md),
[docs/concepts/declaration-scopes/explorer.md](docs/concepts/declaration-scopes/explorer.md),
[docs/cli/lineage.md](docs/cli/lineage.md), [docs/concepts/column-lineage.md](docs/concepts/column-lineage.md),
[docs/cli/dag.md](docs/cli/dag.md), [docs/cli/query.md](docs/cli/query.md),
[docs/concepts/planning.md](docs/concepts/planning.md).
