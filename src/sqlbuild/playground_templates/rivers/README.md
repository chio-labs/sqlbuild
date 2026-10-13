# SQLBuild + Rivers playground

This directory is a Rivers code repository. `definitions.py` orchestrates the SQLBuild waffle
shop project in `waffle_shop/`, which stays a plain SQLBuild project with no Rivers code inside.

## Run Rivers

Install SQLBuild with the Rivers extra, then start Rivers from this directory:

```bash
uv add "sqlbuild[rivers]"
uv run rivers dev definitions
```

You can also run a local materialization directly:

```bash
uv run python definitions.py
```

The repository defines a `waffle_shop` job for UI-triggered materialization.

The definitions use `SqlBuildProject.prepare_if_dev()` to generate
`waffle_shop/target/sqlbuild_dag.json` when `rivers dev` starts with `RIVERS_DEPLOYMENT=dev`.
