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
- Seeds and sources
- SQL unit tests and chain tests
- Built-in and custom audits
- SQL and Python functions
- Macros and custom materialization hooks
- Incremental and partition-oriented model patterns

The local DuckDB database is created as needed when you run build-oriented commands.
