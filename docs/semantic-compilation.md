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
are checked separately; declared return types contribute to inference. SQL and Python UDFs and
table functions are registered with the native catalogue, along with types named in project
contracts and function signatures. Registration does not replace SQLBuild's signature checks.

Known output shapes also validate `unique_key`, `cursor`, `cursor_type`, `cursor_inputs`, custom
`config.partition_column`, `row_diff_exclude_columns`, `row_diff_tolerances.by_column`, source
`cursor_column`, audit expressions/relationships/accepted values, and SQL-test mock/expected names.

Expression type checks are enabled for **DuckDB (including MotherDuck), PostgreSQL, Snowflake,
and BigQuery**. Other adapters retain reference and semantic checks without expression type checks.
`TYPE_CHECKED_DIALECTS` in `compiler/sql_analysis/constants.py` owns this gate.

Only proven bind-time rejections are errors. For example, DuckDB rejects `ordered_at > 5` for a
TIMESTAMP column, but accepts `ordered_at > '2026-01-01'`. Accepted implicit conversions that may
fail on data produce **W21x compile warnings**, with source locations and a warning summary count;
they do not fail compilation. Identical warnings at the same reported location are grouped with
an occurrence count in human output; JSON and the summary retain every occurrence. Unknown input
types never cause type errors. Dialect coercions differ: numeric predicates are accepted by DuckDB
but rejected by PostgreSQL, Snowflake, and BigQuery.
Snowflake's function catalogue is partial and deliberately does not reject unknown function names.
Function signatures and overload coverage remain partial; compilation is not a replacement for
executing SQL unit tests.

Derived-table column aliases, UNPIVOT, and Snowflake GROUPING SETS are checked. DuckDB and Snowflake
reject excess relation aliases; fewer aliases than output columns remain valid. Missing UNPIVOT
input columns are errors.

Project function registration prevents unknown-function errors but does not declare return types to
the validator: some expressions consuming a project function result remain unchecked. Raw external
relations and scope-ordering cases also remain
partially checked. An unknown cast type is a warning because extensions may install that type.

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
| B210–B219 | E210–E219 | Proven native type/shape errors on enabled dialects |
| B216 | E216 | Set-operation, subquery, or row arity |
| B230–B232 | E230–E232 | Grouping, aggregate, and window semantics |
| B233 | E233 | Duplicate scope names, according to dialect rules |
| B234 | E234 | Invalid LIMIT/OFFSET bounds |
| W210–W219 | W210–W219 | Non-blocking runtime-conversion or uncertain-type warnings |
| B300 | SQLBuild | Unknown metadata/audit column |
| B301 | SQLBuild | Incompatible declared metadata, audit, or UDF argument type |
| B302 | SQLBuild | Unknown SQL-test fixture/expected column |

B002–B005 predate these changes and overlap the executor's separately phased build codes. New
semantic codes use distinct ranges. Authored model diagnostics retain source paths and positions.
