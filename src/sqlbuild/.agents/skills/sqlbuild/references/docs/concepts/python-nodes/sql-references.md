<!-- generated-by: sqlbuild skills -->

# SQL References

> Read SQL models and sources from Python nodes without creating SQL dependencies.

Online: https://sqlbuild.com/docs/concepts/python-nodes/sql-references/

Python nodes can **read** SQL models and sources at runtime, but they cannot depend on them as graph edges (see the [SQL boundary](overview.md#the-sql-boundary)). Typed references make this read-only access explicit and safe.

## Declaring a reference

Use `model()` and `source()` from `sqlbuild.refs` in a node's `depends_on`:

```python
from sqlbuild.refs import model, source
from sqlbuild.tasks import task

@task(depends_on=model("fact_orders"))
def export_orders(ctx):
    ...

@task(depends_on=source("raw_orders"))
def inspect_raw(ctx):
    ...
```

Declaring the reference does two things:

1. It tells SQLBuild the node reads that SQL resource, so the node is scheduled **after** the resource is built (read-side).
2. It authorizes `ctx.relation(...)` to resolve that reference at runtime.

It does **not** make the SQL resource depend on the Python node. The dependency is one-way: Python reads SQL, never the reverse.

## Resolving with ctx.relation

Always resolve a reference to its concrete relation with `ctx.relation(...)` instead of hardcoding the table name:

```python
@task(depends_on=model("fact_orders"))
def export_orders(ctx):
    relation = ctx.relation(model("fact_orders"))
    rows = ctx.query(f"SELECT * FROM {relation}").fetchall()
    return ctx.result(metadata={"rows": len(rows)})
```

`ctx.relation(...)` returns the adapter-qualified relation name for the current run. Passing a reference that was not declared in `depends_on` raises an error.

Do not hardcode model or source names in raw SQL. A model's relation depends on the target, its schema and any deferral, so a query like `ctx.query("SELECT * FROM fact_orders")` can fail or read the wrong relation. Always use `ctx.relation(model("fact_orders"))`. SQLBuild checks for this; see [Hard-coded relation names](#hard-coded-relation-names).

## Hard-coded relation names

SQLBuild checks SQL passed to `ctx.query()` and `ctx.execute_sql()` in tasks, assets, and
[Python hooks](../models/hooks/python.md) for names of project relations: models, sources,
and, for hooks, seeds.

**At compile time**, SQL written as a string literal, or as an f-string whose table names are
literal text, is parsed with the project's SQL dialect. Naming a project relation fails to compile
with `P008`:

```
error[P008]: task:export_orders names model:fact_orders as 'fact_orders' in SQL passed to ctx.query()
  --> python/tasks/export.py:9
  = help: declare it with depends_on=model("fact_orders") and use ctx.relation(model("fact_orders")) instead of the relation name
  = help: while migrating a project, allow hard-coded relation names with [references] enforce_explicit = false in sqlbuild_project.toml
```

**At run time**, SQL built dynamically cannot be checked earlier. Before sending it,
`ctx.query()` and `ctx.execute_sql()` parse it in the adapter's dialect, resolve unqualified names
against the current schema, and compare them with the project relations resolved for the run. A
project relation that the node did not obtain through `ctx.relation(...)` produces a `P008`
**warning**. The query still runs. The warning appears in the build summary, counts the node as
`WARN`, and is stored under the node's `warnings` in the `--json` run results.

Both checks ignore:

- Relations resolved through `ctx.relation(...)`, and a hook's own model (`ctx.destination`)
- Relations that are not project relations, such as `information_schema` tables, external tables,
  and temporary tables the node creates
- CTE names
- SQL that cannot be parsed; it is never blocked, only logged at debug level

This is a guard against accidental hard-coding, not a sandbox. SQL sent directly through
`ctx.connection` or `ctx.adapter` is not checked. Checks and loaders cannot declare SQL
references, so their SQL is not checked either. To turn both checks off while migrating a project,
set [`[references] enforce_explicit = false`](../project-configuration.md#references).

## model vs source

| Reference | Resolves to |
|-----------|-------------|
| `model("name")` | The built model relation |
| `source("name")` | The source read relation, following deferred-source semantics |

`source(...)` respects `defer_sources_to`, so a node reading a source in `dev` can read the deferred target's data just like SQL models do.

## Where references are allowed

- **Tasks** and **assets** may declare `model()` and `source()` references and read them with `ctx.relation(...)`.
- **Python hooks** declare the models, sources, and seeds they read with `@hook(reads=...)`; see [Python Hooks](../models/hooks/python.md#declared-reads).
- `seed()` references are accepted by hook reads only; tasks and assets cannot depend on seeds.
- **Checks** may not reference SQL resources. Validate SQL with [audits](../audits.md).
- A Python node referencing a SQL resource never turns into a SQL dependency; selector expansion will not pull Python outputs into SQL model dependencies.
