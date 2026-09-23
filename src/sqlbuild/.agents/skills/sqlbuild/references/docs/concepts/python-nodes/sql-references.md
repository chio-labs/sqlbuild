<!-- generated-by: sqlbuild skills -->

# SQL References

> Read SQL models and sources from Python nodes without creating SQL dependencies.

Online: https://docs.sqlbuild.com/concepts/python-nodes/sql-references

Python nodes can **read** SQL models and sources at runtime, but they cannot depend on them as graph edges (see the [SQL boundary](overview.md#the-sql-boundary)). Typed references make this read-only access explicit and safe across direct and virtual modes.

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

Do not hardcode model or source names in raw SQL. In virtual mode a model resolves to a versioned VDE relation (for example `marts__feature_x.fact_orders`), not the bare name. A query like `ctx.query("SELECT * FROM fact_orders")` will fail or read the wrong relation. Always use `ctx.relation(model("fact_orders"))`.

## model vs source

| Reference | Resolves to |
|-----------|-------------|
| `model("name")` | The built model relation (the VDE logical relation in virtual mode) |
| `source("name")` | The source read relation, following deferred-source semantics |

`source(...)` respects `defer_sources_to`, so a node reading a source in `dev` can read the deferred target's data just like SQL models do.

## Where references are allowed

- **Tasks** and **assets** may declare `model()` and `source()` references and read them with `ctx.relation(...)`.
- **Checks** may not reference SQL resources. Validate SQL with [audits](../audits.md).
- A Python node referencing a SQL resource never turns into a SQL dependency; selector expansion will not pull Python outputs into SQL model dependencies.
