# Native SQL Rules and formatting disposition

SQLBuild owns SQL Rules semantics and canonical formatting while consuming Polyglot as an external
parser dependency. This ledger accounts for every rule in SQLFluff 4.3's 78-rule catalogue and the
prior Sqruff catalogue. A rule is not omitted merely because SQLBuild assigns it somewhere other
than generic SQL analysis.

Disposition meanings:

- **Core compiler**: default native SQL diagnostic, suppressible with a reason.
- **Optional rule**: selected with `[rules].select`; suppressible with a reason.
- **Compiler**: mandatory SQLBuild artifact invariant; ordinary parser/validator behavior for plain SQL.
- **Format**: one deterministic canonical representation, not a configurable warning.
- **project-aware Rules**: a deterministic check that requires SQLBuild resource or repository evidence.
- **Dialect/not applicable**: statement family is outside SQLBuild model queries or already rejected by
  the applicable dialect parser.
- **Drop**: subjective convention whose cost or ambiguity exceeds its generic value.

Rewrite classifications describe formatter-owned transformations: **always**, **conditional**, or **never**. Rules never mutate source. These classifications document shared analysis that `sqb format` may use for deterministic rewrites.

## Aliasing

| Upstream | SQLBuild disposition | Native code | Rewrite | Rationale |
| --- | --- | --- | --- | --- |
| AL01 table alias spelling | Format | — | format | Canonical printer owns explicit `AS` spelling. |
| AL02 column alias spelling | Format | — | format | Canonical printer owns explicit `AS` spelling. |
| AL03 calculated expression alias | Optional rule | `SQBRSQL022` | never | A meaningful output name requires intent. |
| AL04 duplicate table alias | Core compiler | `SQBRSQL009` | never | Ambiguous relation identity; compiler rejects when project evidence is complete. |
| AL05 unused table alias | Optional rule | `SQBRSQL023` | conditional | Remove only aliases without qualified/correlated use or a relation column list. |
| AL06 alias length | Drop | — | never | Arbitrary naming threshold. |
| AL07 forbid aliases | Drop | — | never | Counterproductive for nontrivial joins. |
| AL08 duplicate output alias | Core compiler | `SQBRSQL010` | never | Dangerous output identity; compiler owns managed outer schemas. |
| AL09 self alias | Optional rule | `SQBRSQL016` | always | Exact `name AS name` is redundant. |
| AL10 required derived alias | Compiler/dialect | — | never | Polyglot and the active dialect own syntax requirements. |

## Ambiguity

| Upstream | SQLBuild disposition | Native code | Rewrite | Rationale |
| --- | --- | --- | --- | --- |
| AM01 DISTINCT with GROUP BY | Core compiler | `SQBRSQL006` | always | SQLBuild reports only demonstrably redundant `DISTINCT`. |
| AM02 bare UNION | Optional rule | `SQBRSQL008` | conditional | Use `UNION DISTINCT` only in dialects that accept the explicit spelling. |
| AM03 mixed ORDER direction | Optional rule | `SQBRSQL026` | never | Diagnosis is safe; multi-expression authored edits remain conservative. |
| AM04 unknown output width | Optional rule | `SQBRSQL021` | never | Column enumeration needs schema evidence. |
| AM05 implicit JOIN type | Optional rule | `SQBRSQL025` | always | Conditioned plain `JOIN` is spelled `INNER JOIN`. |
| AM06 mixed ordinal/name references | Optional rule | `SQBRSQL011` | never | Rewriting ordinals needs resolved projection names. |
| AM07 set branch arity | Core compiler | `SQBRSQL020` | never | Invalid branch shape; intended schema requires input. |
| AM08 implicit cartesian join | Core compiler | `SQBRSQL002`, `SQBRSQL003` | conditional | Explicit `CROSS JOIN` only where precedence and authored mapping are proven. |
| AM09 unordered LIMIT/OFFSET | Core compiler | `SQBRSQL004` | never | Ordering keys and tie-breakers require intent. |

## Capitalization

| Upstream | SQLBuild disposition | Rewrite |
| --- | --- | --- |
| CP01 keywords | Format | format |
| CP02 identifiers | Format when dialect semantics permit | format |
| CP03 functions | Format | format |
| CP04 literals | Format | format |
| CP05 data types | Format | format |

SQLBuild has one canonical formatter and does not expose capitalization rule configuration.

## Conventions

| Upstream | SQLBuild disposition | Native code | Rewrite | Rationale |
| --- | --- | --- | --- | --- |
| CV01 inequality spelling | Format | — | format | Canonical operator spelling is presentation. |
| CV02 prefer COALESCE | Drop | — | never | Dialect-native alternatives can differ in typing and evaluation. |
| CV03 trailing comma | Format | — | format | Canonical list layout. |
| CV04 COUNT spelling | Optional rule/simplification | `SQBRSQL017` | always | `COUNT(1)` becomes explicit row-count `COUNT(*)`. |
| CV05 NULL comparison | Core compiler | `SQBRSQL001` | conditional | Right-side equality forms have deterministic `IS` repairs. |
| CV06 terminator | Format | — | format | Canonical statement/file boundary. |
| CV07 statement brackets | Format | — | format | Remove only with equivalence proof. |
| CV08 prefer LEFT JOIN | Drop | — | never | Direction is contextual, not correctness. |
| CV09 blocked words | project-aware Rules | — | never | Repository governance, not generic SQL. |
| CV10 literal quote style | Format | — | format | Normalize only with dialect-safe equivalence. |
| CV11 cast style | Format | — | format | Canonical printer owns spelling without changing types. |
| CV12 hidden join condition | Core compiler | `SQBRSQL002` | conditional | Comma joins become explicit only when precedence is clear. |

## Jinja and layout

| Upstream | SQLBuild disposition | Rewrite |
| --- | --- | --- |
| JJ01 Jinja padding | Not applicable | never | SQLBuild uses Python interpolation rather than Jinja. |
| LT01–LT15 | Format | format | Spacing, indentation, line width, operators, commas, CTE layout, clause breaks, and file newlines belong to the canonical formatter. |

## References

| Upstream | SQLBuild disposition | Native code | Rewrite | Rationale |
| --- | --- | --- | --- | --- |
| RF01 reference absent from scope | Core compiler | `SQBRSQL029` | never | Native SQL analysis reports proven unknown qualifiers; compiler owns schema-resolved failures. |
| RF02 qualify multi-relation columns | Optional rule | `SQBRSQL027` | never | Correct qualifier requires relation-resolution evidence. |
| RF03 consistent single-relation qualification | Optional rule | `SQBRSQL028` | never | Readability policy; do not rewrite several ranges speculatively. |
| RF04 keyword identifiers | Dialect/project-aware Rules | — | never | Dialect parser owns illegal forms; legal naming convention requires project context. |
| RF05 special characters | project-aware Rules | — | never | Project naming convention, not generic correctness. |
| RF06 unnecessary quotes | Format | — | format | Remove only when identifier semantics remain identical. |
| RF07 window alias references | Compiler/dialect | — | never | Scope resolution and active dialect determine legality. |

## Structure

| Upstream | SQLBuild disposition | Native code | Rewrite | Rationale |
| --- | --- | --- | --- | --- |
| ST01 ELSE NULL | Optional rule | `SQBRSQL012` | always | Omission has the same CASE fallback. |
| ST02 simple boolean CASE | Optional rule | `SQBRSQL030` | conditional | Exact TRUE/FALSE shape becomes NULL-safe `COALESCE`. |
| ST03 unused CTE | Core compiler | `SQBRSQL005` | conditional | Remove only authored, comment-safe, select-only, non-recursive dead CTEs. |
| ST04 nested ELSE CASE | Optional rule | `SQBRSQL031` | never | Flattening needs multi-range branch reconstruction. |
| ST05 prefer CTE over subquery | Drop | — | never | Subjective and can harm optimizer/readability choices. |
| ST06 column category order | Drop | — | never | Subjective and potentially schema-breaking. |
| ST07 prefer ON over USING | Drop | — | never | Forms have semantic and output-shape tradeoffs. |
| ST08 DISTINCT parentheses | Optional rule | `SQBRSQL013` | conditional | Rewrite only comment-free, balanced authored forms. |
| ST09 join operand order | Drop | — | never | Cosmetic. |
| ST10 constant predicate | Optional rule | `SQBRSQL014` | never | Removing scaffolding can change intended control flow. |
| ST11 unused join | Optional rule | `SQBRSQL032` | never | Join may intentionally filter or multiply rows. |
| ST12 repeated semicolon | Optional rule/format | `SQBRSQL015` | always | Empty statement terminator is removable. |

## Dialect-specific bundles

| Upstream | SQLBuild disposition | Rationale |
| --- | --- | --- |
| OR01 Oracle empty batch | Dialect/not applicable | SQLBuild model bodies are query expressions; active parser owns batch syntax. |
| PG01 excessive locks | Dialect/not applicable | Transaction/DDL operational behavior is outside model-query Rules. |
| PG02 NOT VALID foreign key | Dialect/not applicable | SQLBuild model bodies do not own PostgreSQL constraint DDL. |
| TQ01 `sp_` procedure prefix | project-aware Rules/not applicable | Procedure naming convention is not generic model SQL. |
| TQ02 procedure BEGIN/END | Dialect/not applicable | Procedure body syntax is owned by the T-SQL parser/compiler. |
| TQ03 empty batch | Format/dialect | Canonical file output removes empty statements where applicable. |
| TQ04 procedure alias spelling | Format/dialect | Canonical spelling only in supported T-SQL statement contexts. |

## SQLBuild-owned additions

| Native code | Disposition | Rewrite | Purpose |
| --- | --- | --- | --- |
| `SQBRSQL007` | Core compiler | never | Positional set operation with star is vulnerable to schema-order drift. |
| `SQBRSQL018` | Core compiler | never | `ROW_NUMBER` without deterministic window ordering is unstable. |
| `SQBRSQL019` | Core compiler | never | Literal NULL in `NOT IN` triggers three-valued anti-filter behavior. |
| `SQBRSQL024` | Optional rule | never | Right-side WHERE reference can null-reject a LEFT JOIN. |
| `SQBRSQL033` | Optional rule | never | Standalone comments attach immediately to a supported syntax node. |
| `SQBRSQL034` | Optional rule | never | Transformation logic remains in top-level CTEs. |
| `SQBRSQL035` | Optional rule | never | The terminal SELECT reads plainly from the final top-level CTE. |
| `SQBRSQL036` | Optional rule | never | CTEs remain at statement top level. |
| `SQBRSQL037` | Optional rule | never | Recursive CTEs require an explicit alternative design. |
| `SQBRSQL038` | Optional rule | never | Explicit cartesian products require a reasoned suppression. |

Schema-dependent nullable `NOT IN`, inferred join cardinality, denominator safety, integer division,
timezone comparison, persisted-output rules, and incremental cursor/replay checks remain compiler or
project-aware Rules work when they need project schema/materialization facts. They are not weakened into syntax-only
generic guesses.

## Current native totals

- 38 SQLBuild-owned generic native rule codes (`SQBRSQL001`–`SQBRSQL038`)
- 12 core defaults
- 26 optional rules selectable by exact code or prefix under `[rules].select`
- 14 always-or-conditionally formatter-rewritable native analysis types
- `SQBRSQL000` suppression validation, with stale standalone directives formatter-rewritable
- five SQLBuild header diagnostics, with whitespace and leading-comment promotion handled when safe

The 33 upstream presentation rules remain formatter-owned rather than inflating the Rules count.
