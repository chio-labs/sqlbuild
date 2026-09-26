# Native binding catalog

Compilation creates a compile-owned native `ProjectCatalog`. Its initial input
contains the dialect, session identifier-case policy, known functions and types,
and ordered relation columns. Compact analysis sends relation references rather
than repeating column objects and function catalogs in every model request.
Native workers assemble the binding schemas and validate the batches.

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

## Diagnostic positions

Native normalization handles SQLBuild relation markers, function markers,
placeholder defaults, and the existing variant-index compatibility transform.
It records character-offset provenance. Native position mapping composes that
provenance with macro-expansion spans and maps both diagnostic endpoints to the
authored SQL. Inputs transformed outside this normalizer use a native alignment
fallback. Python constructs diagnostic and source-location objects from these
results; it no longer runs `SequenceMatcher` or token alignment.

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
