<!-- generated-by: sqlbuild skills -->

# Overview

> SQL model anatomy, references, dependencies, and the model documentation guide.

Online: https://docs.sqlbuild.com/concepts/models

A model is a SQL file that defines one transformation step and produces a table or view in the warehouse.

## Model anatomy

Every model starts with a `MODEL()` header followed by its query:

```sql
MODEL (
  materialized table,
  tags [marts],
  description "Order fact table",
  columns (
    order_id (type INTEGER, audits [not_null]),
  ),
);

SELECT
  o.order_id,
  o.customer_id,
  p.amount_cents
FROM __ref("stg_orders") o
JOIN __ref("stg_payments") p USING (order_id)
```

The header controls how SQLBuild builds, validates, and documents the model. The query remains ordinary SQL apart from SQLBuild reference and macro calls.

## References

| Reference | Syntax | Resolves to |
|-----------|--------|-------------|
| Model | `__ref("name")` | Another model |
| Seed | `__seed("name")` | A seed CSV table |
| Source | `__source("name")` | An external source |
| Scalar UDF | `__udf("name")` | A user-defined function |

SQLBuild discovers the dependency graph from these calls and orders selected work topologically. Among selected models, upstream models run before downstream dependents. An unselected upstream is read from its existing warehouse relation; use an upstream-expanding selector such as `+fact_orders` when it should also be built. Seeds use `__seed()`, not `__ref()`.

See [Functions](functions.md) for scalar UDF and table-function references.

## Model guide

- [Materializations](models/materializations.md): views, tables, incrementals, snapshots, and custom materializations.
- [Schemas](models/schemas.md): inline columns, reusable schemas, inheritance, audits, and model-local extensions.
- [Type Enforcement](models/type-enforcement.md): static type checks and runtime cast behavior by materialization.
- [Contracts](models/contracts.md): exact and open output validation, runtime guarantees, nullability, and enum-backed columns.
- [Hooks](models/hooks.md): SQL and Python lifecycle hooks.
- [Configuration](models/configuration.md): `MODEL()` field reference and SQL-validation controls.

For deeper execution behavior, see [Incremental](incremental.md), [Snapshots](snapshots.md), and [Audits](audits.md).
