# dbt Reuse Playground

A pure dbt project (no SQLBuild models) used to demonstrate SQLBuild's dbt reuse.

The project is a small jaffle-style analytics warehouse with 10 dbt models across
staging, intermediate, and marts, backed by local DuckDB seeds.

When this playground is created, SQLBuild:

1. initializes a git repository and commits the project on `main`
2. builds the `prod` schema once (`dbt run --target prod`) into `warehouse.duckdb`
3. checks out a `dev` branch with a few model edits

This leaves a populated production warehouse so reuse works on the very first
dev build.

## Try

```bash
cd dbt-reuse-playground

# generate the SQLBuild twin project pointing at this dbt project
sqb dbt init --project-dir dbt_project --profiles-dir profiles

# first dev build: SQLBuild reuses unchanged prod tables and rebuilds edited models
sqb dbt build

# second build: no-op
sqb dbt build
```
