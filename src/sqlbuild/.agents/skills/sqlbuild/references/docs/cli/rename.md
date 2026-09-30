<!-- generated-by: sqlbuild skills -->

# rename and mv

> Rename or move a model, or rename a column, and update every reference in one verified step.

Online: https://sqlbuild.com/docs/cli/rename/

`sqb rename` and `sqb mv` change a name everywhere the compiler knows it is used, instead of leaving you to find every `__ref`, fixture, and header by hand. Every edit comes from compiled facts, not text search: a column rename follows the columns each query actually binds, so a same-named column of another table is left alone.

Nothing is written until the edited project compiles. The command applies its edits to a scratch copy of the project, compiles it the way `sqb compile` does, and only then writes the files. If anything cannot be rewritten safely, the command lists those locations and writes nothing.

## Usage

```bash
sqb rename model:<name> <new_name> [flags]
sqb mv model:<name> <path/to/new_file.sql | folder/> [flags]
sqb rename column:<model>.<column> <new_name> [--cascade] [flags]
```

```bash
sqb rename model:stg_orders stg_order_lines
sqb mv model:fact_orders models/reporting/            # keeps the name
sqb mv model:fact_orders models/reporting/order_facts.sql   # moves and renames
sqb rename column:stg_orders.amount revenue
sqb rename column:stg_orders.amount revenue --cascade
```

A model rename keeps the file in its folder and renames it to `<new_name>.sql`. `sqb mv` takes a new file path, which also sets the model name, or a folder ending in `/`, which keeps it.

## What changes

Renaming or moving a model rewrites:

- every `__ref("<name>")` in models, tests, scenarios, audits, hooks, and SQL functions;
- `__ref__<name>` and `__expected__<name>` fixture CTEs in tests and scenarios;
- `cursor_inputs` keys and `relationships (to <name>)` audits in `MODEL` headers.

Renaming a column rewrites the model that produces it and every query that reads it:

- the producing projection, as `amount AS revenue`, or the existing alias;
- every downstream reference, including filters, joins, grouping, and ordering;
- column declarations and column-valued config such as `unique_key`, `cursor`, and `partition_by`, and `cursor_inputs` and `relationships (field ...)` entries that point at the column;
- fixture columns of `__ref__<model>` and `__expected__<model>` CTEs.

By default a column rename is one step: downstream models keep their output names, so `SELECT o.amount` becomes `SELECT o.revenue AS amount`. With `--cascade`, a downstream model that passes the column through unchanged, as a bare column, a same-named alias, or `SELECT *`, renames its output too, and the rename continues through its own consumers.

## History

A renamed model keeps its warehouse history through a [model migration](../concepts/models/migrations.md). When SQLBuild's automatic rename discovery would match the renamed model by its unchanged definition, nothing is added. When it would not, for example because the model calls a UDF or its materialization family changes, the command adds `migrate_from <old_name>` to the model header. The next `sqb build` migrates the relation and leaves a compatibility view at the old name.

A renamed column of an incremental or snapshot model gets `<new> (migrate_from <old>)` in its `columns` block, so the next build renames it in place as a [column migration](../concepts/models/column-migrations.md). Table and view models are rebuilt with the new column anyway; they get the declaration only when the model itself declares `migrate_from`.

The command refuses a rename while the model, or the column, still declares `migrate_from` from an earlier rename. Build it on every target and remove the declaration first.

## Refusals

The command refuses, and writes nothing, when:

- the new name already belongs to another model or column, or the destination file exists;
- a move would take the model out of the scope of a macro, enum, or constant it uses (see [`sqb scope`](scope.md));
- a move would leave no model in the old schema, so the old relation could not be found;
- a reference is produced by a macro, or a column is read inside SQL that a macro generates;
- a column reaches a model through `SELECT *` in a subquery, a `USING` or `NATURAL` join, or an unqualified name that could belong to several tables;
- a downstream model's `SELECT *` would silently rename its output, without `--cascade`;
- Python code or Python node SQL strings name the model or column.

Each location is listed with its file, line, and column. Edit those locations, or pass the model or column to the macro as an argument, and run the command again.

`--allow-manual` applies the safe edits and lists the remaining locations for you to finish. The edited project must still compile; if the remaining locations break it, the command writes nothing and prints the compile errors.

## Flags

| Flag | Description |
|------|-------------|
| `--cascade` | For column renames, rename the output of every downstream model that passes the column through. |
| `--allow-manual` | Apply the safe edits even when some locations must be edited by hand. |
| `--dry-run` | Print every edit and verify the edited project compiles, without writing files. |
| `--json` | Print the result as JSON on stdout. Progress goes to stderr. |

## Output

```text
Rename model  stg_orders -> stg_order_lines
├── models/marts/fact_orders.sql
│   └── 24:13   reference __ref("stg_orders")  ->  __ref("stg_order_lines")
├── models/staging/stg_order_lines.sql  (moved from models/staging/stg_orders.sql)
└── tests/unit/test_fact_orders.sql
    └── 4:1     fixture   __ref__stg_orders  ->  __ref__stg_order_lines
Compiled: ok, 3 files changed
```

With `--json`, the result has `operation`, `target`, `new_name`, `destination`, `status` (`applied`, `dry_run`, `refused`, or `compile_failed`), `files` with every edit, `migrations`, `renamed_columns`, `manual`, `blocking`, and `compile.errors`.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Applied, or a dry run that compiles. |
| `1` | Refused, the edited project did not compile, or the request was invalid. No files were changed. |

## Limitations

- `relationships` audits declared in source or seed YAML files, descriptions, and comments are not rewritten.
- Queries outside the project that read the old relation keep working through the old-name compatibility view until it expires.
