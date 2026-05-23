# SQLBuild Waffle Shop Playground

This project is a local DuckDB playground for SQLBuild. It is self-contained and does not require warehouse credentials.

## Try It

Compile the project:

```bash
sqb compile
```

Build the project locally with DuckDB:

```bash
sqb build
```

After the build creates the local DuckDB objects, run SQL unit tests:

```bash
sqb test
```

Run audits:

```bash
sqb audit
```

Inspect lineage:

```bash
sqb lineage fact_orders
```

## What This Shows

- DuckDB-backed local execution
- SQL models across staging, intermediate, and mart layers
- Seeds, expression-backed sources, and Python source loaders
- SQL unit tests and chain tests
- Built-in and custom audits
- SQL functions
- Macros and custom materialization hooks
- Incremental and partition-oriented model patterns

The local DuckDB database is created as needed when you run build-oriented commands.

## Source Loaders

Two raw tables are populated by Python loaders before the selected model DAG runs:

- `raw__customers` uses a list-returning loader with `write_strategy: table`.
- `raw__orders` uses a generator loader with `write_strategy: delete_insert` and `cursor_column: ordered_at`.

The payment source remains expression-backed, so the project demonstrates both managed source loaders and inline demo data.

Try the loader controls:

```bash
sqb build --no-load      # run models against already-loaded source tables
sqb build --reload       # reload sources while leaving models incremental
sqb load                 # run only source loaders
```
