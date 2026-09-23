<!-- generated-by: sqlbuild skills -->

# init

> Scaffold a new SQLBuild project.

Online: https://docs.sqlbuild.com/cli/init

# sqb init

Creates a new SQLBuild project with a minimal directory structure and configuration files.

## Usage

```bash
sqb init
```

No flags. Run in the directory where you want to create the project.

## Project layout

`sqb init` creates the configuration, linter settings, and empty resource directories needed for a standalone project:

```text
my-project/
  sqlbuild_project.toml
  .sqruff
  models/
    staging/
    marts/
  schemas/
  sources/
  seeds/
  loaders/
  tasks/
  assets/
  checks/
  hooks/
    sql/
    python/
  tests/
    unit/
    scenarios/
  functions/
    sql/
    python/
  macros/
  audits/
    generic/
    singular/
```

Empty directories contain `.gitkeep` files so the scaffold can be committed. Reusable attached
audit definitions belong in `audits/generic/`; standalone audits belong in `audits/singular/`.
Add reusable SQL lifecycle hooks to `hooks/sql/` and decorated Python lifecycle hooks to
`hooks/python/`; see [Hooks](../concepts/models/hooks.md).

The generated project uses DuckDB, creates a named `local` connection shared by `dev` and
`prod`, and defaults models to table materialization. Its configuration follows this shape:

```toml
adapter = "duckdb"
default_target = "dev"

[connections.local]
database = "my_project.duckdb"

[targets.dev]
connection = "local"
schema = "dev"

[targets.prod]
connection = "local"
schema = "prod"
```

The project name is derived from the current directory name, with hyphens converted to
underscores.
