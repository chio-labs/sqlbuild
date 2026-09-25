<!-- generated-by: sqlbuild skills -->

# playground

> Create a self-contained SQLBuild project to explore locally.

Online: https://docs.sqlbuild.com/cli/playground

# sqb playground

Creates a self-contained waffle shop project with DuckDB. No warehouse credentials, no git clone, no external data - just a working project you can compile, build, test, and explore immediately.

## Usage

```bash
sqb playground [name]
```

The positional argument is the directory to create (default `sqlbuild-playground`). The template is chosen with `--template` (default `waffle_shop`).

## Templates

| Template | Description |
|----------|-------------|
| `waffle_shop` | Default. DuckDB-backed project with models, tests, scenarios, and macros. |
| `dagster` | Waffle shop project plus a `dagster/` directory with a ready-to-run `definitions.py`. |
| `rivers` | Waffle shop project plus a `rivers_pipeline/` directory with a Rivers repository definition. |
| `python_nodes` | A small DuckDB project demonstrating [Python nodes](../concepts/python-nodes/overview.md): a task feeding a loader, a model read by a Python asset through `ctx.relation(model(...))`, a soft-skip fan-in, `materialized=False`, and a Python check. |

## What it creates

A complete DuckDB-backed project with:

- Staging views, fact/dimension tables, and incremental models
- Sources with inline expression data (no external setup)
- Seeds, SQL functions, and a custom materialization
- Built-in and custom audits
- SQL unit tests and multi-model tests
- E2E scenario tests
- Python macros
- AI agent skill files (auto-installed for OpenCode, Claude Code, and other agents)

The `dagster` template adds:

- `dagster/definitions.py` - Dagster definitions with `sqlbuild_assets`, `sqlbuild_scenario_checks`, and `SqlBuildCliResource`
- `dagster/README.md` - Setup instructions

The `python_nodes` template instead creates a focused Python-nodes project:

- `tasks/orders.py`, `loaders/orders.py`, `assets/orders_export.py`, `checks/orders_export.py`
- A `fact_orders` SQL model over a managed `raw_orders` source
- Examples of the SQL boundary, `ctx.relation(model(...))`, soft-skip fan-in, and a Python check

## Examples

```bash
# Default waffle shop
sqb playground waffle-shop
cd waffle-shop
sqb build

# With Dagster integration
sqb playground --template dagster
cd sqlbuild-playground
uv pip install 'sqlbuild[dagster]'
dagster dev -f dagster/definitions.py

# With Rivers integration
sqb playground --template rivers
cd sqlbuild-playground
uv pip install 'sqlbuild[rivers]'
uv run rivers dev rivers_pipeline.definitions

# With Python nodes
sqb playground --template python_nodes
cd sqlbuild-playground
sqb build --select +fact_orders --select +orders_export
sqb check --select +check_orders_export
```

## Notes

- The target directory must not already exist
- DuckDB is included as a core dependency - no extra installation needed
- The local DuckDB database file is created on the first build
- The Dagster template uses `prepare_if_dev()` to auto-generate the DAG artifact when Dagster starts in dev mode
