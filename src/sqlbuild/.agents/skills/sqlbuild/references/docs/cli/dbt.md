<!-- generated-by: sqlbuild skills -->

# sqb dbt

> Coordinate dbt and SQLBuild projects.

Online: https://sqlbuild.com/docs/cli/dbt/

Orchestrate dbt and SQLBuild together. Each subcommand runs dbt first, then SQLBuild, with selection logic across both project graphs. dbt remains responsible for dbt-owned models; SQLBuild validates and executes SQLBuild-owned models downstream. See [Using SQLBuild with dbt](../concepts/dbt-compatibility/overview.md) for scope and selection behavior.

## sqb dbt plan

Preview combined dbt and SQLBuild work without executing.

```bash
sqb dbt plan [--select <selector>...] [--exclude <selector>...] [--json] [--verbose]
```

Shows which dbt models will run, which SQLBuild models will run, and the dbt/SQLBuild commands that would be executed.

## sqb dbt run

Run dbt models first, then SQLBuild models.

```bash
sqb dbt run [--select <selector>...] [--exclude <selector>...]
```

## sqb dbt build

Build dbt models first (including dbt tests), then SQLBuild models with audits.

```bash
sqb dbt build [--select <selector>...] [--exclude <selector>...]
```

### Plan safety policies

After dbt finishes, `sqb dbt run` and `sqb dbt build` apply the same plan safety policies as
[`sqb build`](build.md) before any SQLBuild model executes: blocked model and column
migrations, compatibility-view conflicts, the target's `execution_limits.max_models`, the
snapshot full-refresh policy, `table_type_downgrade`, `time_travel_retention_decrease`, and
`missing_migration_origin`. `sqb dbt` has no `--allow-*` flags. A policy that requires
confirmation asks for the typed confirmation on an interactive terminal and refuses otherwise;
build the affected models with `sqb build` and its allow flag instead, or relax the policy. A
refusal at this point leaves completed dbt work in place and builds no SQLBuild models.

## sqb dbt debug

Run dbt diagnostics followed by SQLBuild diagnostics.

```bash
sqb dbt debug [--no-connection]
```

## Selectors

All `sqb dbt` commands accept `--select` and `--exclude`. Selectors work across both dbt and SQLBuild:

```bash
# SQLBuild model with dbt dependencies
sqb dbt build --select downstream_orders

# Full upstream chain including dbt
sqb dbt build --select +downstream_orders

# Downstream of modified dbt models
sqb dbt build --select state:modified+

# SQLBuild models by tag
sqb dbt build --select tag:nightly

# SQLBuild models by path
sqb dbt build --select path:models/marts

# Exclude by tag
sqb dbt build --select fact_orders+ --exclude tag:nightly
```

See [Selection](../concepts/dbt-compatibility/selection.md) for full details on how selectors route work between dbt and SQLBuild.

## Configuration

Configure the dbt project location in `sqlbuild_project.toml`:

```toml
[dbt]
project_dir = "../dbt_project"
profiles_dir = "../profiles"
target_path = "../dbt_project/target"
```

See [Project Configuration](../concepts/project-configuration.md#dbt) for all fields.
