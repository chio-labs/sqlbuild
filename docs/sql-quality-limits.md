# Project-wide SQL quality limits

SQL quality Rules are compile errors when selected. Family selectors such as
`SQBRSQL` include new Rules on upgrade; projects using exact-code selectors must
add the new codes explicitly.

## Ranking sort expressions: SQBRSQL043

```toml
[rules]
select = ["SQBRSQL043"]
max_ranking_order_by = 4
```

`max_ranking_order_by` is a positive integer, default **4**, configured once in
`sqlbuild_project.toml`. Zero is invalid, not a disable switch. Changing the limit
invalidates cached SQL Rule results.

The Rule counts ORDER BY expressions in ROW_NUMBER, RANK, DENSE_RANK,
FIRST_VALUE and LAST_VALUE windows, including named windows and ranking calls in
QUALIFY. A compound expression is one expression; non-ranking aggregates are not
subject to this cap. There is no automatic fix because selecting priorities and
tie-breakers requires author intent.

Long ranking sorts usually encode a priority. Compute a named priority column in
an earlier CTE (CASE or a lookup seed), then order by that priority, the few
meaningful sort columns, and a unique tie-breaker.

## Disallow model-local overrides

```toml
[rules]
allow_model_overrides = false
```

The default is `true`, preserving existing behavior. When `false`, compilation
rejects `MODEL (sql_analysis false)`, inline `-- sqb: ignore ...` directives,
`rules.rule_ignores` (path or selector ignores), and `rules.rule_exceptions`
(exact-path exemptions), and path-scoped `rules.select_star_allow` exemptions.
Diagnostics name the forbidden override. This policy is
checked independently of selected Rules and cached findings. Remove the override
and correct the SQL; there is no model-local switch to relax the project policy.
