<!-- generated-by: sqlbuild skills -->

# Writing Macros

> Write Python functions that generate reusable SQL fragments at compile time.

Online: https://sqlbuild.com/docs/concepts/macros/

## Contents

- Create a macro
- Call a macro from SQL
- Arguments
- Keep implementation details private
- Use macros in tests
- Use macros in hooks
- Where macros work
- Next steps

Macros are Python functions that generate SQL during compilation. They provide reusable,
parameterized SQL without introducing a separate template language.

## Create a macro

Put project-wide macros in Python files under the top-level `macros/` directory:

```text
my_project/
├── macros/
│   ├── currency.py
│   └── test_helpers.py
├── models/
└── sqlbuild_project.toml
```

Every public function defined by a macro file becomes callable from SQL:

```python
# macros/currency.py
def cents_to_dollars(expression: str) -> str:
    """Convert a cents expression to dollars."""
    return f"ROUND(CAST({expression} AS DOUBLE) / 100, 2)"
```

## Call a macro from SQL

Use `@macro_name(...)` in a model query:

```sql
MODEL (
  materialized table,
  tags [marts],
);

SELECT
  order_id,
  @cents_to_dollars("amount_cents") AS amount_dollars
FROM __ref("stg_orders")
```

During compilation, SQLBuild replaces the call with the function's returned SQL:

```sql
ROUND(CAST(amount_cents AS DOUBLE) / 100, 2)
```

A macro used directly in SQL must return a string.

## Arguments

Macro calls accept Python literal values:

- Strings: `"value"` or `'value'`
- Numbers: `42`, `3.14`, `-1`
- Booleans: `True`, `False`
- Lists: `[1, 2, 3]`
- Dictionaries: `{"key": "value"}`
- `None`
- The result of another macro call

Positional and keyword arguments are supported:

```sql
@mock_orders(count=5, status="completed")
```

Use quoted strings when passing SQL expressions such as column names. The macro decides how to
place that text into its returned SQL.

## Keep implementation details private

Only public functions owned by the file are exported as macros. Prefix helpers, constants, classes,
and type aliases with `_`:

```python
# macros/orders.py
_DEFAULT_STATUS = "completed"

def _status_filter(status: str) -> str:
    return f"status = '{status}'"

def completed_orders() -> str:
    return _status_filter(_DEFAULT_STATUS)
```

Here, SQL may call `@completed_orders()`. `_status_filter` and `_DEFAULT_STATUS` remain ordinary
Python implementation details.

Imported functions are not re-exported as new macros from the importing file.

## Use macros in tests

Tests are SQL, so they can use macros as reusable fixture generators:

```python
# macros/test_helpers.py
def mock_orders(count: int = 1) -> str:
    rows = [
        f"SELECT {i} AS id, {i * 100} AS customer_id, 'completed' AS status"
        for i in range(1, count + 1)
    ]
    return " UNION ALL ".join(rows)
```

```sql
TEST();

WITH
__source__raw__orders AS (
  @mock_orders(3)
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status
  UNION ALL
  SELECT 2 AS order_id, 200 AS customer_id, 'completed' AS status
  UNION ALL
  SELECT 3 AS order_id, 300 AS customer_id, 'completed' AS status
)
SELECT 1
```

## Use macros in hooks

Macros work inside inline and named SQL hooks:

```python
# macros/permissions.py
def grant_target(target: str) -> str:
    return f"GRANT SELECT ON {target} TO analyst_role"
```

```sql
MODEL (
  post_hooks [inline_sql('@grant_target(@@CTX:destination.qualified)')],
);

SELECT 1 AS id
```

See [SQL Hooks](models/hooks/sql.md) for hook lifecycle and context syntax.

## Where macros work

Macros are supported in:

- Model query SQL
- Inline and named SQL hooks
- Unit tests and scenarios
- Standalone audit SQL
- SQL functions and supported inline source expressions

Macros are not accepted in ordinary `MODEL()` configuration fields. SQL hook entries are the
exception because their contents are SQL.

## Next steps

    Compose macros through Python imports and use adapter or target context.
    Limit a macro to one folder, or to that folder and its child folders.
