# Contract adoption

SQLBuild validates SQL and authored contracts offline during ordinary compilation. It does not
download warehouse schemas as part of `sqb compile`.

When adopting an existing physical schema, use the explicit online `contract` command. The target
named by `--from` supplies only the database/schema namespace to inspect. SQLBuild uses the active
project connection for the inspection and never resolves a second set of origin credentials.

```bash
# Compare code with selected physical relations. No files or relations are changed.
sqb contract diff --from prod --select tag:finance

# Print the same adoption findings without changing source.
sqb contract generate --from prod --select tag:finance

# Fill missing types and append missing physical columns in repository declarations.
sqb contract generate --from prod --select tag:finance --write

# Explicitly replace conflicting physical names/types and remove declarations absent physically.
sqb contract generate --from prod --select tag:finance --write --overwrite

# Sources are first-class selectable resources.
sqb contract diff --from prod --select source:raw_orders
```

`diff` returns exit code `0` when declarations agree and `1` when differences exist. Operational
and configuration failures remain command errors. JSON output is available with `--json` and
contains the evidence namespace, resource identity, finding kind, and declared/physical types. It
never includes connection credentials.

## Safety and ownership

- `--from` is read-only. Contract commands do not mutate warehouse relations, state, fingerprints,
  or lifecycle records.
- Generation changes repository declarations only when `--write` is present.
- Additive generation preserves existing types on conflicts, existing columns absent physically,
  comments, descriptions, audits, nullability, enums, tags, freshness, and loader configuration.
- `--overwrite` is the explicit repository replacement policy. It is not a warehouse write.
- Generation does not add `contract enforced`; activation remains an authored policy decision.
- A shared `SCHEMA()` is never changed from one model's evidence. SQLBuild reports an ownership
  conflict instead.
- Files marked as generated are not hand-edited.
- Writes are atomic. SQLBuild reparses and recompiles the project, restoring exact prior contents
  if validation fails.

## SQL analysis and contracts

`settings.sql_analysis` is the single public compiler analysis gate. It controls syntax analysis,
column binding, expression typing, output inference, and semantic validation. The corresponding
model override is `sql_analysis false`, and the CLI escape hatch is `--no-sql-analysis`.

The legacy `settings.sql_validation`, model `sql_validation`, and `--no-sql-validation` spellings
remain compatibility aliases. Conflicting old and new configuration values are rejected.

An enforced upstream contract is an authoritative compile-time interface. Missing or ambiguous
column references fail in projections, joins, filters, grouping, `HAVING`, `QUALIFY`, windows, and
ordering. Complete derived CTE/subquery/model shapes can also prove absence. Partial or opaque input
schemas remain open: SQLBuild does not turn missing metadata into a false negative assertion.

Direct non-projection uses can be requested separately from value-producing column lineage:

```bash
sqb lineage fact_orders --include-uses --format json
```

The `semantic_uses` payload groups direct resolved columns by contexts such as `join_on`, `where`,
`group_by`, `having`, `qualify`, `window_partition_by`, `window_order_by`, and `order_by`. These facts
are intentionally not emitted as `ColumnLineageEdge` values and are not propagated transitively.

Compile-time binding does not replace runtime enforcement. Persisted tables and incrementals still
use staged contract/type validation before target mutation. Views receive static validation but do
not receive runtime cast reconstruction. `sqb plan` remains responsible for online physical drift
and execution decisions.
