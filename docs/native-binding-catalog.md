# Native binding catalog

Compilation creates a compile-owned native `ProjectCatalog`. Its initial input
contains the dialect, session identifier-case policy, known functions and types,
and ordered relation columns. Compact analysis sends relation references rather
than repeating column objects and function catalogs in every model request.
Native workers assemble the binding schemas and validate the batches.
Catalog validation releases the GIL and uses a bounded Rayon pool of up to four
workers. Clause checks and schema validation share the parsed AST.

Inferred relations are registered as they become available. A request can mark a
relation open or provide a local schema override. Physical source validation
forks the catalog with the planner's inspected column shapes; those shapes do not
mutate the offline compile catalog or leak into a subsequent rebind. Catalog
handles are process-local and excluded from the custom Rule host's serialized
project.

## Identifier semantics

For case-insensitive quoted identifiers, SQLBuild folds binding identifiers in
the parsed native AST and schema. It retains the SQL text and original spans,
and restores authored names in diagnostics. SQL without a double quote bypasses
AST identifier folding. This does not require a Polyglot source modification or
a Python token-dictionary round trip. For example:

```sql
SELECT "orderid" FROM (SELECT 1 AS "OrderId") q
```

With Snowflake's `QUOTED_IDENTIFIERS_IGNORE_CASE` enabled, the derived alias
resolves. Type checks still run on the resolved expression.
For SQL without double quotes, the compiler reuses fused semantic validation even
when this session setting is enabled. Reuse requires the final input schemas to
match the schemas used for that validation.

## Diagnostic positions

Native normalization handles SQLBuild relation markers, function markers,
placeholder defaults, and the existing variant-index compatibility transform.
It records character-offset provenance. Native position mapping composes that
provenance with macro-expansion spans and maps both diagnostic endpoints to the
authored SQL. Inputs transformed outside this normalizer use a native alignment
fallback. Python constructs diagnostic and source-location objects from these
results; it no longer runs `SequenceMatcher` or token alignment.
Compact compilation normalizes inputs in one native batch. Deferred binding and
diagnostic location construction reuse the resulting SQL rather than repeating
normalization for each consumer or diagnostic.

Native diagnostics carry SQLBuild codes, severity, messages, and span facts.
Validation guard failures are explicit errors, rather than discarded native
diagnostics. The validation parser supports the compiler's deeper expression
workloads while retaining a bounded complexity guard.

## Opaque parser expressions

An opaque parser node remains an unevaluated Rules fault. SQLBuild does not
rewrite a predicate to hide incomplete parsing. This synthetic Snowflake query
currently reproduces an opaque `raw` predicate directly in Polyglot 0.13.2:

```sql
SELECT 1 AS order_id
WHERE NOT SPLIT_PART('orders:pending', ':', 2) LIKE 'pending%'
```

The parser must represent the predicate as typed NOT/LIKE expressions before
Rules can claim complete evaluation. A source location attached to a spanless
refusal can be the query-body fallback, rather than the predicate's position.
## CTE output-slot usage facts

The native analysis boundary exposes `analyze_cte_slots_batch_json`. Its input is
`{"requests": [{"sql": "...", "dialect": "duckdb", "schema": {"tables": []}}]}`.
Schema is optional; supply the compiler's input relation columns to resolve stars
and otherwise ambiguous inputs. Each result is independently `Ok` or `Err`, in
request order. An unresolved binding is an error, never evidence that a slot is
unused.

The version-1 compact `Ok` document contains:

- `strings`: interned scope paths, CTE names and column names.
- `ctes`: rows `(scope_index, name_index, distinct, set_operation, model_output,
  explicit_column_aliases)`.
- `slots`: rows `(cte_index, zero_based_ordinal, output_name_index, read,
  semantically_required)`.

The identity is the lexical CTE scope plus ordinal, not terminal source lineage.
For example, an intermediate literal-valued `priority` read only in a later
WHERE clause is marked read even though it has no physical upstream column.
Qualification and scope resolution are native AST operations. Nested CTEs and
shadowed names retain distinct identities; aliases, stars, filters, joins,
grouping, window clauses and correlated subqueries participate in usage.
Set-operation outputs and read set-operation inputs carry the semantic-required
flag. Incomplete star schemas or unprovable alias lists fail with a reason.
