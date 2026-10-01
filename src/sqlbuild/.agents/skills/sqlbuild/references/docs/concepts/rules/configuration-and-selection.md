<!-- generated-by: sqlbuild skills -->

# Configuration and selection

> Select built-in and custom Rules by exact code or family prefix.

Online: https://sqlbuild.com/docs/concepts/rules/configuration-and-selection/

## Contents

- Codes and families
- Rule options
- Focused selection
- Join keys and final CTE names
- SQL quality limits and ranking determinism

Configure built-in and custom Rules together:

```toml
[rules]
select = ["SQBRSQL", "SQBRGRAPH", "XSQBRARCH"]
ignore = ["SQBRSQL004"]
```

An empty `select` disables configurable Rules. It does not disable mandatory compiler correctness.

## Codes and families

Built-in codes use `SQBR<FAMILY><three digits>`, such as `SQBRSQL004`, `SQBRMODEL101`, and
`SQBRGRAPH101`. Custom codes use `XSQBR<optional uppercase family><three digits>`, such as
`XSQBRARCH001`.

A family is always the code with its final three digits removed:

```text
SQBRSQL004    → SQBRSQL
XSQBRARCH001  → XSQBRARCH
XSQBR001      → XSQBR
```

Exact codes select one Rule. Prefixes select every matching Rule. `ignore` uses the same matching
semantics and takes precedence over `select`.

Use the catalogue to inspect available codes and metadata:

```bash
sqb rules list
sqb rules show SQBRSQL004
```

## Rule options

Built-in and Custom Rules can declare typed options. Configure them by exact code:

```toml
[rules.rule_options.XSQBRNAME001]
required_prefix = "order"

[rules.rule_options.SQBRTEST203]
allowed_tests = ["customers__reviewed_empty_input"]
```

`SQBRTEST203` (`empty-input-only-test`) accepts `allowed_tests`, a list of SQL test names that are
reviewed exceptions. Listed tests are not flagged and still count toward `SQBRTEST202`'s
`min_tests_per_model`. Entries that name no existing test are reported as stale. See
[Empty-input tests](../testing.md#empty-input-tests).

Unknown Rule codes, option names, and invalid option values fail configuration.

## Focused selection

Run one exact Rule or family while developing or adopting it:

```bash
sqb rules run SQBRSQL004
sqb rules run SQBRSQL
sqb rules run XSQBRARCH --select customer_orders
```

Focused execution constructs the compiler facts needed by the selected Rules. It does not replace
the complete configured enforcement performed by `sqb compile`.

  See every `sqb rules` command and exit code.

## Join keys and final CTE names

`SQBRSQL040` checks every `JOIN ... ON` in the SQL covered by SQL Rules, including joins inside CTEs
and subqueries. `USING (...)` is accepted. Allowed predicates are:

- Plain column comparisons, including equality, inequality, range and null-safe comparisons.
- A plain column compared with a literal, including a signed numeric literal.
- Literal-only predicates such as `ON TRUE`, `ON FALSE` and `ON 1 = 1`, including
  `LEFT JOIN LATERAL FLATTEN(...) AS f ON TRUE`. Functions or casts applied to literals are still
  computed expressions.
- `BETWEEN` / `NOT BETWEEN` on a plain column with plain-column or literal bounds.
- `IN` / `NOT IN` on a plain column with a literal list.
- `IS NULL` / `IS NOT NULL` on a plain column.
- Parenthesized predicates, and `AND` or `OR` combinations in which every branch is allowed.

Functions, casts (including `::`), arithmetic, concatenation, `CASE`, subqueries and other computed
operands are findings. For example, replace `ON LOWER(o.category) = c.category_key` with a CTE that
projects `LOWER(category) AS category_key`, then join `ON o.category_key = c.category_key`. Snowflake
variant path access such as `ON a.data:key = b.id` is also computed: project the value as a named
column before joining.

`SQBRSQL041` checks CTE naming: the last top-level CTE must be named `final` (compared
case-insensitively, including quoted identifiers), and no other CTE, including a nested one, may use
that name. Queries without CTEs are unaffected, and SQL-test fixture CTEs are exempt. `SQBRSQL035`
owns the terminal `SELECT`'s plain projection from that last CTE, so select both, normally through
the `SQBRSQL` family, for the complete convention. Parentheses around the entire query do not create
a nested CTE scope.

## SQL quality limits and ranking determinism

These Rules are errors with project-wide limits. No model can opt out of a limit locally.

```toml
# sqlbuild_project.toml
[rules.thresholds]
max_literal_length = 100   # default
max_ranking_order_by = 5   # default
```

- `SQBRSQL042`: every output column of a non-final CTE must be read later in the same model,
  in any clause of a later CTE or the final query, including through a later `SELECT *`
  pass-through. The last CTE (the model output), unreachable CTEs (reported by `SQBRSQL005`),
  CTEs with a column list, recursive queries and SQL-test fixtures are exempt. A later step that
  uses an `@` interpolation in an expression may read any column, so it keeps every column, and
  interpolated outputs are never reported. A later step that reads the CTE as a whole row (the
  alias itself, as in `HASH(g)` or `COUNT(DISTINCT g)`), through a star nested in an expression
  (`HASH(g.*)`), through `COLUMNS(...)`, or through `SELECT DISTINCT *` or a grouped `SELECT *`
  reads every column. An output alias reused in the CTE's own `WHERE`, `GROUP BY`, `HAVING`,
  `QUALIFY` or `ORDER BY` is read. A `GROUP BY` key can be dropped from the output while it stays
  in `GROUP BY`.
  `sqb format --fix` removes an unused column only when the removal keeps every row: the column
  must be a column reference or a deterministic scalar expression (no aggregate, window,
  set-returning or table function, subquery, or volatile function), and the CTE must not use
  `SELECT DISTINCT`, `DISTINCT ON`, `GROUP BY ALL`, `ORDER BY ALL`, an aggregate without
  `GROUP BY`, or positional `GROUP BY`/`ORDER BY`. Other findings are reported without a fix and
  name the reason. The fix repeats until nothing changes.
- `SQBRSQL043`: `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `FIRST_VALUE` and `LAST_VALUE` windows may
  sort by at most `max_ranking_order_by` expressions. Order by the one or two columns that decide
  which row wins, then a unique row key as the final tie-breaker. If the rows have no unique
  column, build one in the upstream model from the columns that identify a row (for example
  `HASH(source_partition, source_offset, line_index) AS row_key`) and declare it with a `unique`
  audit, so `SQBRSQL018` can prove the order. Raise the project limit only when the order
  genuinely needs more keys.
- `SQBRSQL044`: a string literal longer than `max_literal_length` characters is an error. Define
  the value once as a [constant](../constants.md) in the narrowest
  [scope](../declaration-scopes.md) that covers every use, and reference it with
  `@const`: a model-private `constants (_status_pattern '...')` entry in the `MODEL` header when
  only that model uses it; a `CONSTANT (name status_pattern, value '...');` file in
  `_sqlbuild/_constants/` (that folder only) or `_sqlbuild/constants/` (that folder and below) of
  the nearest folder holding every use; top-level `constants/` only for project-wide values.
  Otherwise shorten the literal. When the identical literal is reported in other files, the help
  lists them (up to five) and names the nearest common folder and its constants directory.
  Literals produced by `@const` or a macro are not reported, and there is no automatic fix.
- `SQBRSQL018` requires every `ROW_NUMBER`, `FIRST_VALUE` and `LAST_VALUE` window to be proven
  deterministic: `PARTITION BY` and `ORDER BY` together must cover a unique key of the ranked rows.
  Keys come from `unique` column audits and model-level `unique` audits naming a column, when the
  column is also non-null (a `not_null` audit or `nullable false`), and from the `unique_key` of
  incremental `merge` models and of `delete_insert` models matched by key without a cursor.
  Snapshot, append, microbatch and cursor-ranged `delete_insert` `unique_key`s do not prove one
  row per key. Keys are followed through projections, renames, filters, one-to-one joins,
  `GROUP BY` grains (named or positional), `SELECT DISTINCT`, `UNION`, and
  `ROW_NUMBER() ... = 1` deduplication in `QUALIFY` or a later `WHERE`; a `QUALIFY` key holds for
  later steps, never for the window that defines it. A join that can match a row more than once,
  `UNION ALL`, and relations without a declared key lose the proof, and "cannot prove" is an
  error. To comply, declare the key upstream (for example
  `columns (order_id (audits [unique, not_null]))`), or end the order with a unique
  tie-breaker, building a row key upstream when none exists. `RANK` and
  `DENSE_RANK` give tied rows the same value, so they need no proof.

A finding that `sqb format --fix` can fix says so in text output and carries `"fixable": true` in
`sqb rules --json run` output; `sqb compile` adds the same note to the diagnostic.

Family selectors such as `select = ["SQBRSQL", "SQBRMODEL", "SQBRGRAPH"]` pick up new built-in Rules
on upgrade, so a release that adds `SQBRSQL040` to `SQBRSQL044` can expose computed join keys,
differently named final CTEs, unused CTE columns, long literals or ranking sorts that were accepted
before.
