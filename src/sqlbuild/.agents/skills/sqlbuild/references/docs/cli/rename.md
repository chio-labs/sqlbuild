<!-- generated-by: sqlbuild skills -->

# rename and mv

> Rename or move a model, or rename a column, and update every reference in one verified step.

Online: https://sqlbuild.com/docs/cli/rename/

## Contents

- Usage
- What changes
- History
- Refusals
- Flags
- Output
- Exit codes
- Limitations

`sqb rename` and `sqb mv` change a name everywhere the compiler knows it is used, instead of leaving you to find every `__ref`, fixture, and header by hand. Every edit comes from compiled facts, not text search: a column rename follows the columns each query actually binds, so a same-named column of another table is left alone.

Nothing is written until the edited project compiles. The command applies its edits to a scratch copy of the project, compiles it the way `sqb compile` does, and only then writes the files. If anything cannot be rewritten safely, the command lists those locations and writes nothing.

## Usage

```bash
sqb rename <model> <new_name> [flags]
sqb mv <model> <path/to/new_file.sql | folder/> [flags]
sqb rename <model>.<column> <new_name> [--cascade] [flags]
```

```bash
sqb rename stg_orders stg_order_lines
sqb mv fact_orders models/reporting/            # keeps the name
sqb mv fact_orders models/reporting/order_facts.sql   # moves and renames
sqb rename stg_orders.amount revenue
sqb rename stg_orders.amount revenue --cascade
```

Targets are written the way [`sqb lineage`](lineage.md) reads them: a bare name is a model, and `<model>.<column>` is one of its columns. The `model:` and `column:` prefixes are optional, so `sqb rename model:stg_orders stg_order_lines` and `sqb rename column:stg_orders.amount revenue` still work. A target that names a source, seed, or function is refused, because those are not renamed by these commands.

A model rename keeps the file in its folder and renames it to `<new_name>.sql`. `sqb mv` takes a new file path, which also sets the model name, or a folder ending in `/`, which keeps it.

## What changes

Renaming or moving a model rewrites:

- every `__ref("<name>")` in models, tests, scenarios, audits, hooks, and SQL functions;
- `__ref__<name>` and `__expected__<name>` fixture CTEs in tests and scenarios;
- `cursor_inputs` keys, `relationships (to ...)` audits, and `__ref("<name>")` inside quoted SQL in `MODEL` headers and reusable `SCHEMA` declarations;
- `relationships` audits (`to:` and `field:`) and `__ref("<name>")` in source and seed YAML.

Moving a model to another folder also moves the macros, enums, constants, reusable schemas, generic audits, and named hooks it uses when their [placement](../concepts/declaration-scopes/placement.md) must change, following the same rules `sqb compile` enforces:

- a declaration only the moved model uses moves with it, into the destination folder's matching role;
- a declaration other resources still use moves to the lowest folder they share, for example `models/staging/_sqlbuild/macros/`;
- when that folder would be an authored root such as `models/`, or the users span resource trees such as models and tests, it moves to the top-level role (`macros/`, `enums/`, `constants/`, `schemas/`, ...).

Declarations are moved, never copied. Folders the move leaves empty are removed.

Renaming a column rewrites the model that produces it and every query that reads it:

- the producing projection, as `amount AS revenue`, or the existing alias;
- every downstream reference, including filters, joins, grouping, and ordering;
- column declarations and column-valued config such as `unique_key`, `cursor`, and `partition_by`, and `cursor_inputs` and `relationships (field ...)` entries that point at the column;
- fixture columns of `__ref__<model>` and `__expected__<model>` CTEs.

By default a column rename is one step: downstream models keep their output names, so `SELECT o.amount` becomes `SELECT o.revenue AS amount`. With `--cascade`, a downstream model that passes the column through unchanged, as a bare column, a same-named alias, or `SELECT *`, renames its output too, and the rename continues through its own consumers.

## History

A renamed model keeps its warehouse history through a [model migration](../concepts/models/migrations.md). Whenever the model's relation moves and its materialization keeps warehouse data (table, view, incremental, or snapshot), the command adds `migrate_from <old_name>` to the model header, so the move does not depend on automatic discovery finding exactly one match. The next `sqb build` migrates the relation and leaves a compatibility view at the old name. A move that keeps the relation, such as a folder change in the same schema, adds nothing.

On a target that never built the old name, the origin is missing. By default the plan warns and the model builds fresh; set [`missing_migration_origin`](../concepts/project-configuration.md#missing-migration-origins) on a target to require confirmation or stop the build instead.

A renamed column of an incremental or snapshot model gets `<new> (migrate_from <old>)` in its `columns` block, so the next build renames it in place as a [column migration](../concepts/models/column-migrations.md). Table and view models are rebuilt with the new column anyway; they get the declaration only when the model itself declares `migrate_from`.

The command refuses a rename while the model, or the column, still declares `migrate_from` from an earlier rename. Build it on every target and remove the declaration first.

## Refusals

The command refuses, and writes nothing, when:

- the new name already belongs to another model or column, or the destination file exists;
- a declaration a moved model uses must change folder, but its file also holds declarations that must stay, or it is not an authored project file, or a file with its name already exists at the new folder;
- a move would leave no model in the old schema, so the old relation could not be found;
- a reference is produced by a macro, or a column is read inside SQL that a macro generates;
- a column reaches a model through `SELECT *` in a subquery, a `USING` or `NATURAL` join, or an unqualified name that could belong to several tables;
- a downstream model's `SELECT *` would silently rename its output, without `--cascade`;
- Python code or Python node SQL strings name the model or column.

Each location is listed with its file, line, and column, with the fix. Edit those locations, or pass the model or column to the macro as an argument, and run the command again. The command never applies part of a rename.

References produced by a macro are only possible when a project turns off explicit references (`[references] enforce_explicit = false`); such projects get the refusal list for them.

## Flags

| Flag | Description |
|------|-------------|
| `--cascade` | For column renames, rename the output of every downstream model that passes the column through. |
| `--dry-run` | Print every edit and verify the edited project compiles, without writing files. |
| `--json` | Print the result as JSON on stdout. Progress goes to stderr. |

## Output

```text
Rename model  stg_orders -> stg_order_lines
├── models/marts/fact_orders.sql
│   └── 24:13   reference __ref("stg_orders")  ->  __ref("stg_order_lines")
├── models/staging/stg_order_lines.sql  (moved from models/staging/stg_orders.sql)
│   └── 1:8     migration + migrate_from stg_orders
└── tests/unit/test_fact_orders.sql
    └── 4:1     fixture   __ref__stg_orders  ->  __ref__stg_order_lines
Migrations
└── stg_order_lines  migrate_from stg_orders  keeps the relation's history and its old name working
Compiled: ok, 3 files changed
```

With `--json`, the result has `operation`, `target`, `new_name`, `destination`, `status` (`applied`, `dry_run`, `refused`, or `compile_failed`), `files` with every edit, `migrations`, `renamed_columns`, `manual`, `blocking`, and `compile.errors`.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Applied, or a dry run that compiles. |
| `1` | Refused, the edited project did not compile, or the request was invalid. No files were changed. |

## Limitations

- Descriptions and comments are not rewritten.
- Queries outside the project that read the old relation keep working through the old-name compatibility view until it expires.
