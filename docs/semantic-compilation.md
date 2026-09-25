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

## Reading diagnostics

Diagnostics use one layout: headline, resource and location, source snippet with a span underline,
notes, then code-specific help. SQL-test diagnostics include their authored fixture snippet and
use `sql test: name`, just as model diagnostics use `model: name`. JSON retains the location's
exclusive `end_line`/`end_column` boundary, notes, and help.

An unknown column identifies its input and authored alias. Suggestions use edit distance with a
bounded typo cutoff and recognize short abbreviations such as `qty`. No suggestion is printed when
none is close. The available-column note puts the closest names first and shows at most ten names.

```text
error[B002]: Unknown column 'qty' in stg_orders (as o)
  model: fact_orders
  --> models/marts/fact_orders.sql:16:5
     |
  16 |   o.qty,
     |     ^^^
  = note: stg_orders has: quantity, status, waffle_type_id, customer_id, order_id, ordered_at
  = note: 2 downstream uses of fact_orders.quantity were not checked because of this error
  = help: did you mean 'quantity'?
```

Type errors report uppercase types and available operand evidence, for example
`o.ordered_at is TIMESTAMP, 5 is INTEGER`. Comparison help recommends a literal appropriate to the
type family and dialect. Native spans are mapped back through normalization and macro expansion;
simple binary expressions are underlined in full. Diagnostics without usable spans keep the
authored query-start fallback. Per-operand labels and per-code documentation links are separate
follow-ups.

Error recovery treats poisoned output names and their downstream lineage as provisional. A
downstream error traceable only to that root is suppressed and counted in a root-error note;
independent errors on other columns and other inputs remain errors. Recovery does not silence a
whole dependent query or make its unchecked uses valid. Affected models remain in
`semantic_checks_partial`, including on warm/cache-hit runs.

Located binding and type errors also make the affected projection's type unknown. That uncertainty
propagates through column lineage. Failed dependants are checked again with only those input types
unknown; an independent error on another column or input remains visible. Root notes count unchecked
downstream output uses, including transitive uses. Contract type checks do not emit a secondary
unknown-type warning for those same poisoned outputs. If native evidence cannot locate the failing
projection, recovery retains the diagnostic rather than opening the entire input.

Temporal cursor metadata accepts DATE, DATETIME, and TIMESTAMP families interchangeably, including
Snowflake timestamp variants. A timestamp cursor on a string, numeric, or Boolean column still
produces B301.

Snowflake binding honours `QUOTED_IDENTIFIERS_IGNORE_CASE = true` from the effective target's
connection `session_parameters`, for both offline declared schemas and warehouse-backed rebinding.
False or absent settings preserve the dialect's existing case rules. For example:

```toml
[targets.analytics]
schema = "preserve"

[targets.analytics.connection]
session_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = true }
```

The setting participates in the analysis-cache identity. Identifier folding is token-based and
does not alter string literals, comments, or authored SQL. Diagnostic offset mapping is lazy and
uses a bounded cache of token alignments, shared by all diagnostics on the same normalized query.

The single human partial-check notice groups model names by reason, gives the relevant repair or
rerun command, and truncates long lists. `sqb compile --json` contains the full selected-model
reason map. Unknown output types and unresolved stars are reported as explicitly as open sources;
the notice never reduces them to a count alone.

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
