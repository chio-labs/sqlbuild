# Semantic compilation

`sqb compile` stays offline. It validates SQL references against each input separately, including
models with no relation inputs. A join to an open source does not disable checks on a closed input.
An unqualified name that could belong to an open input cannot be rejected offline.

## Authoritative column names

- Enforced model and source contracts, seeds, and declared table-function outputs are closed shapes.
- Expression sources have the column names inferred from their SQL expression.
- An explicit model projection defines its output names even over an open input. Types propagate
  through dependencies where they can be inferred; an unknown type does not make the names unknown.
- A star over closed inputs expands; a star over an open input remains open.
- Declaring some columns on a table source does **not** declare its complete shape. Use
  `contract: enforced` when those declarations are complete.

Adopt a physical source schema with:

```sh
sqb contract generate --from <target> --select source:raw_orders --write
```

`sqb plan` and `sqb build` recheck source readers against inspected physical columns before model
execution. Existing bulk metadata is reused. Selected table sources omitted from that metadata
are inspected in database-grouped batches: one relation-list call and one bulk-column call per
database, using the adapter's normal metadata batching. Missing managed sources and ambiguous
unqualified physical names stay open.

## Checks and limits

Binding checks apply to SQL clauses, CTEs, subqueries, and expanded macros. Semantic grouping,
aggregate and window-placement diagnostics are errors. Project UDF arity and known argument types
are checked separately; declared return types contribute to inference. Project functions are
excluded from native unknown-function diagnostics until the native catalogue accepts declarations.

Known output shapes also validate `unique_key`, `cursor`, `cursor_type`, `cursor_inputs`, custom
`config.partition_column`, `row_diff_exclude_columns`, `row_diff_tolerances.by_column`, source
`cursor_column`, audit expressions/relationships/accepted values, and SQL-test mock/expected names.

General expression type checking is **not enabled yet**. The native literal and dialect coercion
catalogue must first distinguish errors from valid expressions such as
`ordered_at > '2026-01-01'`. The supported dialects are controlled in one place:
`TYPE_CHECKED_DIALECTS` in `compiler/sql_analysis/constants.py`, initially empty. Mapping for native
E210–E219 is ready for that integration. Function-catalogue and structural coverage also depend on
the native engine; compilation is not a replacement for executing SQL unit tests.

One notice summarizes partial semantic checks. `sqb compile --json` includes per-model reasons in
`semantic_checks_partial`; progress and notices go to stderr. The notice does not increment the
diagnostic warning count.

Escape hatches are `MODEL (sql_analysis false)`, the corresponding path default, and
`--no-sql-analysis`. Disabling SQL analysis also disables inference and lineage for that model.

## Diagnostic codes

| SQLBuild | Native | Meaning |
|---|---|---|
| B002 | E201 | Unknown column |
| B003 | E221 | Ambiguous column |
| B004–B005 | E222–E223 | Reference/scope errors |
| B101 | E202 | Unknown function |
| B102 | E203 or project declaration | Invalid function arity |
| B210–B219 | E210–E219 | Native type/shape errors (type checking gated) |
| B216 | E216 | Set-operation arity; native emission currently shares the type-check gate |
| B230–B232 | E230–E232 | Grouping, aggregate, and window semantics |
| B300 | SQLBuild | Unknown metadata/audit column |
| B301 | SQLBuild | Incompatible declared metadata, audit, or UDF argument type |
| B302 | SQLBuild | Unknown SQL-test fixture/expected column |

B002–B005 predate these changes and overlap the executor's separately phased build codes. New
semantic codes use distinct ranges. Authored model diagnostics retain source paths and positions.
