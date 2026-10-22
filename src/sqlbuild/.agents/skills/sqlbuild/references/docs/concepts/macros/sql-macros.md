<!-- generated-by: sqlbuild skills -->

# SQL Macros

> Write typed, logic-free SQL fragments that the compiler checks and sees inside.

Online: https://sqlbuild.com/docs/concepts/macros/sql-macros/

## Contents

- Create a SQL macro
- Call a SQL macro
- Parameter types
- Parameters in the body
- Compose macros
- Checks and tools
- Choose the right tool

A SQL macro is a reusable piece of SQL with typed parameters. Unlike a
[Python macro](../macros.md), it holds no logic: its body is SQL, so the compiler checks
it on its own, expands it in place, and formatting, rules and column lineage see through every
call.

A SQL macro is one of three forms, decided by how its body starts:

| Body starts with | Form | Called |
|---|---|---|
| anything else | expression | where an expression belongs, such as a select item or a `WHERE` clause |
| `WITH` | CTE list | between the CTEs of a `WITH` list |
| `SELECT` | column list | as an item of a select list |

## Create a SQL macro

Put each SQL macro in its own `.sql` file under `macros/sql/`. The file name is the macro name.
Python macros live next to it in `macros/python/`:

```text
my_project/
├── macros/
│   ├── python/
│   │   └── labels.py
│   └── sql/
│       ├── cents_to_dollars.sql
│       ├── clean_orders.sql
│       └── audit_columns.sql
├── models/
└── sqlbuild_project.toml
```

A file directly under a `macros/` folder fails with `D013`, which names the subfolder to move it
to. Folder scopes use the same layout, such as `models/marts/_sqlbuild/_macros/sql/`.

A SQL macro file starts with a `MACRO` header, then the body:

```sql
-- macros/sql/cents_to_dollars.sql
MACRO (
  description "Cents to dollars",
  arguments (amount_cents BIGINT, places INT CONST DEFAULT 2),
  returns DECIMAL(18, 2),
);

ROUND(CAST(@amount_cents AS DECIMAL(18, 4)) / 100, @places)
```

`returns` is required for expression macros and not allowed for the other forms.

## Call a SQL macro

Every macro call says its kind: `@sql.name(...)` calls a SQL macro and `@py.name(...)` a Python
macro. A bare `@name(...)` fails with `P014`, which names both spellings.

Arguments are SQL, positional or named with `name := value`:

```sql
SELECT
  o.order_id,
  @sql.cents_to_dollars(o.fee_cents + o.tax_cents, places := 0) AS fees
FROM __ref("stg_orders") AS o
```

compiles to:

```sql
SELECT
  o.order_id,
  ROUND(CAST((o.fee_cents + o.tax_cents) AS DECIMAL(18, 4)) / 100, 0) AS fees
FROM analytics.stg_orders AS o
```

An argument is parenthesised where the body needs it. Arguments resolve in the caller's scope, so a
model can pass its own private constant; the macro receives only the value.

### CTE lists

A CTE-list macro inserts its CTEs, with its own names, into the caller's `WITH` list at the call:

```sql
-- macros/sql/clean_orders.sql
MACRO (
  description "Deduplicated, non-deleted orders",
  arguments (src RELATION (order_id BIGINT, updated_at TIMESTAMP, is_deleted BOOLEAN)),
);

WITH live AS (SELECT * FROM @src WHERE NOT is_deleted),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) AS row_num
  FROM live
),
latest AS (SELECT * EXCLUDE (row_num) FROM ranked WHERE row_num = 1)
```

```sql
WITH orders_raw AS (SELECT * FROM __ref("stg_orders")),
@sql.clean_orders(orders_raw)
final AS (SELECT order_id, amount FROM latest)
SELECT * FROM final
```

The compiled model holds `orders_raw`, `live`, `ranked`, `latest` and `final`, flat and in that
order, and later CTEs may read any of the macro's CTEs. Commas around the call are optional;
`sqb format` normalises them.

### Column lists

A column-list macro inserts its columns into the caller's select list. Every column needs a name:

```sql
-- macros/sql/audit_columns.sql
MACRO (
  description "Standard audit columns",
  arguments (src RELATION (created_at TIMESTAMP, updated_at TIMESTAMP)),
);

SELECT @src.created_at, @src.updated_at, @src.updated_at > @src.created_at AS was_updated
```

`SELECT o.order_id, @sql.audit_columns(o) FROM orders AS o` compiles to
`SELECT o.order_id, o.created_at, o.updated_at, o.updated_at > o.created_at AS was_updated FROM orders AS o`.

Use a column list when the same ordered set of columns repeats, for example in every branch of a
`UNION ALL`.

A CTE or column name a macro inserts that the caller already defines fails with `P018`, which names
both. Nothing is renamed, so a model cannot call the same CTE-list macro twice.

## Parameter types

Every parameter has a type, and may have a `DEFAULT`:

| Type | Accepts |
|---|---|
| `BIGINT`, `VARCHAR`, `TIMESTAMP`, ... | Any SQL expression of a compatible type, evaluated per row: a column, arithmetic, a function call, a literal or a constant. |
| `<type> CONST` | Only a value known at compile time: a literal, a scalar constant, an enum value, or a `CONST` parameter of a calling macro. A column or expression fails with `P017`. Scalar types only. |
| `LIST <type>`, `SET <type>` | An inline list or set, or a list or set constant. Always compile-time, so they take no `CONST`. They render like constants. |
| `ENUM <name>` | A member of that enum, such as `@enum("order_status").OPEN`. |
| `RELATION (<columns>)` | A CTE name, a table alias, or `__ref()`, `__source()` or `__seed()`, with at least these columns. |
| `COLUMN OF <relation>` | A column name of that relation parameter. |

SQL types are written as in [schema declarations](../models/schemas.md) and checked against the
adapter's SQL dialect the same way, including the dialect's array types such as `VARCHAR[]`. A
runtime array value uses the array type; `LIST VARCHAR` is a list known at compile time.

Leave `CONST` off unless the body needs a literal. `CONST` is part of the macro's contract: callers
can no longer pass a column.

## Parameters in the body

Write every parameter as `@name` in the body, as [generic audits](../audits.md) do. A bare
identifier is always plain SQL, a column, CTE or table, never the parameter:

```sql
-- macros/sql/is_status.sql
MACRO (
  description "Whether the status column matches",
  arguments (status VARCHAR),
  returns BOOLEAN,
);

status = @status
```

Here `status` is the caller's column and `@status` the argument. A relation parameter is qualified
directly, as `@src.created_at` or `@src.*`, or aliased, as `FROM @src AS s` and then `s.created_at`.

These fail with `P022`:

- an `@name` that names no parameter; the error lists the parameters
- a relation parameter written bare where it would read a table, such as `FROM src` or
  `src.created_at`; the error says `src is a parameter of macro clean_orders(); write @src`

Parameters may not be named `sql`, `py`, `const`, `enum` or `param`.

### Positions that need a literal

SQL needs a literal in some positions. A parameter without `CONST` there fails with `P023` when the
macro is checked:

```
error[P023]: places is used where a literal is required; declare it places INT CONST
```

| Position | Adapters |
|---|---|
| `LIMIT`, `OFFSET`, `TOP` and `FETCH FIRST` counts | all |
| `INTERVAL` and `EXTRACT` units | all |
| `PIVOT ... IN (...)` values | all |
| `DATE_TRUNC` unit (the first argument, or the last on BigQuery) | all |
| `ROUND` precision | DuckDB and MotherDuck (for `DECIMAL` values), Databricks |

The positions every adapter shares are checked for every macro file. `DATE_TRUNC` and `ROUND` are
checked for the project's adapter at each call.

## Compose macros

A SQL macro may call other SQL macros, and pass its own parameters on as `@name`:

```sql
-- macros/sql/net_amount.sql
MACRO (
  description "Net amount in dollars",
  arguments (gross_cents BIGINT, refund_cents BIGINT),
  returns DECIMAL(18, 2),
);

@sql.cents_to_dollars(@gross_cents - COALESCE(@refund_cents, 0))
```

Macros that call each other in a cycle fail with `P019`. SQL and Python macros never call each
other (`P020`); compose them in the model by passing results, as in
`@py.bracket(@sql.cents_to_dollars(o.amount_cents))`. A SQL macro and a Python macro may not share
a visible name.

A body may not call `__ref()`, `__source()` or `__seed()` (`P016`): pass relations in as `RELATION`
arguments. `@const(...)` and `@enum(...)` in a body resolve from the macro file's own folder, like
audits and unlike Python macros; one that is not visible from there fails with `S026`. Make it a
parameter and pass the value from the caller instead.

## Checks and tools

Each macro is checked on its own when the project compiles, and again in every model after
expansion, so a missing relation column or misspelled `COLUMN OF` argument fails like any other
unknown column in the model. Errors point at the call and at the macro file.

- `sqb format` formats SQL macro files and normalises the commas around CTE-list and column-list
  calls. Expression bodies are left as written.
- [Rules](../rules.md) and [column lineage](../column-lineage.md) read the expanded
  SQL, so they see through every call.
- Editing a macro recompiles its callers.

Test SQL macros with [macro-mode unit tests](../testing.md#macro-tests), and replace one
in a model test with a [`__macro__` mock](../testing.md#macro-mocking).

## Choose the right tool

| Use | When |
|---|---|
| SQL macro | The fragment is plain SQL with typed inputs: a calculation, a filter, a set of CTEs or columns you repeat. The compiler sees inside it. |
| [Python macro](../macros.md) | Generating the SQL needs logic: loops, conditions on arguments, the adapter or target, or reading project context. |
| [SQL function](../functions.md) | The logic belongs in the warehouse, to be called by other tools or evaluated per row there, or it is too large to inline everywhere. |
| [Generic audit](../audits.md) | The SQL checks data quality on a model rather than producing part of its query. |

Prefer a SQL macro over a Python macro whenever no logic is needed: its calls stay readable,
typed and checked, and every tool sees the SQL it produces.
