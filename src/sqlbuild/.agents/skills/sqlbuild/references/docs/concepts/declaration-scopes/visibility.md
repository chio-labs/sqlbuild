<!-- generated-by: sqlbuild skills -->

# How Visibility Works

> See which enums, constants, and macros are available to each SQL file.

Online: https://docs.sqlbuild.com/concepts/declaration-scopes/visibility

## Contents

- Start from the SQL file
- Supported resource trees
- Which file controls visibility?
- Tests and expected output
- Macros importing macros
- Names do not shadow

For most SQL, the rule is simple:

> A file can use declarations available to the whole project, declarations in unprefixed roles
> under `_sqlbuild/` folders owned beside or above it, and declarations in an underscored role owned
> directly beside it.

## Start from the SQL file

SQLBuild starts from the file containing the SQL and walks up that file's directory tree. The folder
directly containing the file is its **owner folder**.

```text
models/
├── constants/                 available throughout models/
│   └── warehouse.sql
└── commerce/
    ├── _sqlbuild/
    │   ├── enums/             available throughout commerce/
    │   │   └── order_status.sql
    │   └── _constants/        available directly in commerce/ only
    │       └── minimum_value.sql
    ├── orders.sql
    └── history/
        └── archived_orders.sql
```

From this tree:

| File | Can use |
|------|---------|
| `orders.sql` | `warehouse`, `order_status`, and `minimum_value` |
| `history/archived_orders.sql` | `warehouse` and `order_status` |

`minimum_value` is not available in `history/` because `_sqlbuild/_constants/` applies only to files
directly in the `_sqlbuild/` owner's folder.

## Supported resource trees

Grouped declaration directories can be placed below these SQL resource roots:

| Root | Contents |
|------|----------|
| `models/` | Models and inline model hooks |
| `tests/unit/` | Unit tests |
| `tests/scenarios/` | Scenarios |
| `hooks/sql/` | Named SQL hooks |
| `functions/sql/` | SQL functions |
| `audits/` | Audits |
| `sources/` | Inline source expressions |

Each root is a separate tree. For example, `models/constants/` does not make declarations available
under `tests/`. Put a declaration in the top-level `constants/`, `enums/`, or `macros/` directory
when it must be available across different resource trees. Project-root `_constants/`, `_enums/`,
and `_macros/` directories are invalid because there is no owner folder at the project root for
them to be private to.

Existing scoped declaration roles directly below an owner remain supported. `_sqlbuild/` is the
preferred layout because it keeps all declarations together without changing their visibility.
Only the six public/private declaration-role directories are valid directly under `_sqlbuild/`;
other entries are rejected. `_sqlbuild/` must sit below a concrete owner directory. A project-root
`_sqlbuild/` or authored-root path such as `models/_sqlbuild/` is invalid; use the project-wide
`macros/`, `enums/`, or `constants/` roots at that boundary.

## Which file controls visibility?

| SQL being compiled | SQLBuild starts from |
|--------------------|----------------------|
| Model query | The model file |
| Inline SQL hook in a model | The model file |
| Unit test SQL | The test file, plus inferred tested-resource relationships |
| Scenario SQL | The scenario file, plus expected-model enum and constant relationships |
| Named SQL hook | The hook file under `hooks/sql/` |
| SQL function | The function file under `functions/sql/` |
| Audit | The audit file |
| Inline source expression | The source definition |

This means a reusable named hook does not change meaning depending on which model calls it. The
hook uses declarations available where the hook itself is stored.

## Tests and expected output

A test first sees declarations available from its own folder tree. It may also use file-based
macros, enums, and constants available to a model for which it defines expected output.

```sql
TEST();

WITH
__expected__orders AS (
  SELECT
    1 AS order_id,
    @normalize_order_status("'completed'") AS normalized_status,
    @enum("order_status").COMPLETED AS status
)
SELECT 1
```

Because the test defines `__expected__orders`, the test may use file-based macros, enums, and
constants available to `orders`, including declarations in exact-owner-private roles.
Scope Explorer describes this as **available through expected output for model `orders`**. This is
an additional relationship, not another visibility level.

This additional access does **not** include:

- Enums or constants declared privately inside the model's `MODEL()` header
- Declarations from a model merely mentioned by filename or directory layout

Only an explicit `__expected__model_name` section adds the model's eligible file-based declarations.
When a test checks several models, SQLBuild combines the declarations available through all
expected models and makes that deterministic union available while compiling the entire test.

Macro-mode tests receive the tested macro and the file-based declarations available from that
macro's production owner. SQLBuild infers tested macros from calls in `__macro_actual__`; the test's
filename or directory does not grant production visibility.

```text
models/orders/_sqlbuild/_macros/order_policy.py
tests/unit/macros/models/orders/test_order_policy__returns_quantity.sql
```

The macro test can call `order_policy` without promoting it to the project-wide `macros/` root. A
test can also use helper macros scoped to its own test directory:

```text
tests/unit/orders/
├── _sqlbuild/
│   └── macros/
│       └── fixtures.py
└── test_orders__calculates_total.sql
```

Those helpers remain unavailable to production resources. Mocked model, source, seed, and dbt
fixture CTEs do not grant declarations from the mocked resource's production scope.

## Macros importing macros

A macro file may import another project macro file when the imported macro is available from the
importing file's location. The same directory rules apply as they do to SQL.

```python
# models/commerce/macros/orders.py
from macros.currency import round_money

def formatted_total(expression: str) -> str:
    return round_money(expression)
```

A broadly available macro cannot import a macro from a narrower child or sibling directory. See
[Composition and Context](../macros/composition-and-context.md) for complete examples.

## Names do not shadow

Public names must be unique within their feature:

- One public macro name cannot be defined twice.
- One public enum name cannot be defined twice.
- One public constant name cannot be defined twice.

Moving a declaration into a narrower directory changes where it is available; it does not create a
second version that overrides another declaration.

Macros, enums, and constants use separate namespaces, so these three references may coexist:

```sql
@format_currency()
@const("format_currency")
@enum("format_currency").USD
```

  Choose the simplest directory that matches where a declaration is used.
