# dbt Playground

A pure dbt project (no SQLBuild models) used to demonstrate SQLBuild's
change-aware dbt builds, clone, and diff.

The project is a small jaffle-style analytics warehouse with 10 dbt models across
staging, intermediate, and marts, backed by local DuckDB seeds.

When this playground is created, SQLBuild:

1. initializes a git repository and commits the project on `main`
2. builds the `prod` schema once (`dbt run --target prod`) into `warehouse.duckdb`
3. checks out a `dev` branch with a few model edits

This leaves a populated `prod` schema and a `main`/`dev` branch pair, so you can
compare and clone production relations against your dev branch.

## Try

```bash
cd dbt-playground

# generate the SQLBuild twin project pointing at this dbt project
sqb dbt init --project-dir dbt_project --profiles-dir profiles

# first build: SQLBuild builds the selected dbt models
sqb dbt build

# second build: change-aware - unchanged dbt models are pruned from the dbt run
sqb dbt build

# compare your dev branch against the production-shaped main branch
sqb dbt diff --select fct_orders

# clone production relations into your target without rebuilding
sqb dbt clone --select fct_orders
```
