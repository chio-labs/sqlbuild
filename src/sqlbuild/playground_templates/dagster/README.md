# SQLBuild + Dagster playground

This directory is a Dagster code location. `definitions.py` orchestrates the SQLBuild waffle
shop project in `waffle_shop/`, which stays a plain SQLBuild project with no Dagster code inside.

## Run Dagster

Install SQLBuild with the Dagster extra, then start Dagster from this directory:

```bash
uv add "sqlbuild[dagster]"
DAGSTER_IS_DEV_CLI=1 uv run dagster dev -f definitions.py
```

Open the Dagster UI, materialize the `waffle_shop_assets` asset group, then run the scenario checks.

The definitions use `SqlBuildProject.prepare_if_dev()` to generate
`waffle_shop/target/sqlbuild_dag.json` when Dagster starts in dev mode.
