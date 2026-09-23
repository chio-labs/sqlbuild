# Macros, enums, constants and where they live

## Contents

- Macros
- Constants and enums
- Model-private values
- Interpolation
- Placement and visibility
- Diagnosing visibility problems

## Macros

Macros are plain Python functions that return final SQL strings. Every public function in a macro
file is callable from SQL as `@name(...)`; prefix helpers, constants and classes with `_`.

```python
# macros/currency.py
def cents_to_dollars(expression: str) -> str:
    return f"ROUND(CAST({expression} AS DOUBLE) / 100, 2)"
```

```sql
SELECT order_id, @cents_to_dollars("amount_cents") AS amount_dollars
FROM __ref("stg_orders")
```

- Arguments are Python literals: strings, numbers, `True`/`False`, lists, dicts, `None`, or another
  macro call. Pass SQL expressions and column names as quoted strings. Keyword arguments work:
  `@mock_orders(count=5, status="completed")`.
- A macro used in SQL must return a string, and its output is final SQL. Never return text
  containing another `@macro()` call; compose by calling the Python functions directly, including
  functions imported from other visible macro files (`from macros.currency import add_tax`).
- Macros work in model SQL, SQL hooks, unit tests, scenarios, audits, SQL functions and inline
  source expressions. They are not allowed in ordinary `MODEL()` configuration fields.
- Imported functions keep their original identity; they are not re-exported by the importing
  file. Import cycles and imports from outside the file's scope are rejected.

## Constants and enums

Declared in `.sql` files; one file can hold several declarations.

```sql
-- constants/commerce/thresholds.sql
CONSTANT (name min_items, value 7);
CONSTANT (name fallback_source, value "web");

-- enums/order_status.sql
ENUM (
  name order_status,
  members [PLACED, COMPLETED, CANCELLED],
);
ENUM (
  name source,
  members (WEB "web", PARTNER "partner"),
);
```

Use `@const("min_items")` and `@enum("order_status").COMPLETED` in SQL. SQLBuild validates names
and members at compile time and renders safe literals for the adapter. Constants are data (strings,
integers, booleans, floats, exact decimals, `null`, lists and objects), never raw SQL snippets; use a
macro when you need SQL.

## Model-private values

Values used by one model belong in its header, with underscore names:

```sql
MODEL (
  enums (
    _state [OPEN, CLOSED],
  ),
  constants (
    _min_items 2,
  ),
);

SELECT * FROM __ref("order_batches")
WHERE state = @enum("_state").OPEN AND item_count > @const("_min_items")
```

They are visible only in that model's query and its inline SQL hooks, not in tests, scenarios,
other models or named hooks.

## Interpolation

| Syntax | Meaning |
|---|---|
| `@@name` | Project variable (`[vars]`, overridable with `--vars '{"name": ...}'`) |
| `@@ENV:NAME` | Environment variable at compile time |
| `@@CTX:name` | Destination relation, target or run ID; SQL hooks only |
| `${ENV:NAME}` | Environment variable inside TOML or YAML config values |

## Placement and visibility

| Location | Visible to |
|---|---|
| Top-level `macros/`, `enums/`, `constants/` | The whole project |
| `<folder>/_sqlbuild/macros/` (also `enums/`, `constants/`) | That folder and all folders below |
| `<folder>/_sqlbuild/_macros/` (also `_enums/`, `_constants/`) | Files directly in that folder |
| Underscored value in `MODEL()` | That model only |

Declarations never flow upward or to siblings. `_sqlbuild/` may contain only those six role
folders and must sit below a concrete owner folder (not the project root or `models/` itself).
Older projects may use role folders such as `models/marts/_macros/` directly under the owner; they
remain supported.

**Narrowest placement is enforced.** SQLBuild computes the lowest common owner folder of every
consumer. A declaration placed wider than needed, for example a top-level macro used only under
`models/commerce/`, is rejected at compile. When adding a declaration:

1. Find every file that will use it.
2. Put it in the nearest folder containing all of them: `MODEL()` for one model, `_sqlbuild/_<role>/`
   for one folder, `_sqlbuild/<role>/` for one folder tree, top level only for separate trees such
   as models and tests.
3. Run `sqb compile` and `sqb scope`. A misplaced declaration fails with `S024`, which names the
   required folder, for example `Move it to 'models/marts/_sqlbuild/_constants/'`.

## Diagnosing visibility problems

```bash
sqb scope model:orders --explain macro:formatted_order_total   # why visible or not; required placement
sqb scope model:orders --include-nearby                        # close declarations out of reach
sqb scope --at models/finance/revenue.sql                      # what a new file there could use
sqb scope model:orders --as-path models/finance/orders.sql      # effect of moving a model
```

Full reference: [docs/concepts/macros.md](docs/concepts/macros.md),
[docs/concepts/macros/composition-and-context.md](docs/concepts/macros/composition-and-context.md),
[docs/concepts/constants.md](docs/concepts/constants.md), [docs/concepts/enums.md](docs/concepts/enums.md),
[docs/concepts/model-private-values.md](docs/concepts/model-private-values.md),
[docs/concepts/interpolation.md](docs/concepts/interpolation.md),
[docs/concepts/declaration-scopes.md](docs/concepts/declaration-scopes.md).
