# Compiler cache architecture

The compiler cache exists to avoid proving unchanged facts again. It must never turn an uncertain
input into a cache hit, and a missing, stale, corrupt, oversized, or contended cache must behave like
an ordinary uncached compile.

This document defines the target architecture. The current vertical slice implements versioned
model-analysis entries, dependency-aware compact analysis generations, shared SQL-test closure
indexes, bounded compact-generation retention, corruption fallback, and analysis hit/miss telemetry.
Project inventory, discovery/attachment reuse, and command snapshots remain later layers; their
sections below are design constraints rather than claims of current implementation.

## Goals

- Make unchanged fresh-process compiles proportional to project inventory and requested output, not
  total SQL complexity.
- Make a small edit proportional to the changed resource and its semantic dependents.
- Reuse downstream analysis when an upstream implementation changes without changing its exported
  column interface.
- Preserve diagnostics, bindings, types and nullability, lineage, tests, audits, hooks, macros,
  ordering, artifacts, and exit codes exactly.
- Keep cache data project-local, bounded, inspectable, non-executable, and safe under concurrent
  compiler processes.

## Non-goals

- The cache is not a second source of project truth.
- The cache does not make arbitrary Python execution deterministic. A stage with dynamic inputs that
  are not represented in its identity must bypass persistent reuse.
- The cache does not store pickles, code objects, callables, imported modules, adapter instances, or
  open connections.
- The cache does not replace warehouse execution state or change build selection semantics.

## Layers

### 1. Project inventory

The inventory records every compiler-owned authored input as a normalized project-relative path,
resource role, content digest, size, and filesystem identity metadata. Configuration, ignore files,
adapter identity, compiler and SQL-analysis engine versions, selected target, CLI variables, and
compile modes are explicit identity inputs.

Filesystem metadata may identify an unchanged candidate, but reusable semantic facts remain
content-addressed. Ambiguous or concurrently changing observations are misses. Added, removed,
renamed, and role-changing paths are first-class changes.

### 2. Static discovery facts

Parsing results for SQL, YAML, CSV metadata, and statically inspected Python declarations are keyed
by content digest, parser version, resource role, and parse options. These records contain only
validated JSON-compatible values. Runtime Python discovery still imports current project code and
is never reconstructed from executable cache data.

### 3. Attached resource facts

Attachment resolves configuration, declarations, macros, hooks, schemas, tests, and references.
Each record carries the exact identities it observed:

- authored resource content;
- effective target, variables, and relevant configuration;
- visible enum and constant declarations;
- macro implementation and dependency closure;
- referenced schema or hook declarations;
- adapter rendering contract.

If any observed identity is absent or unstable, that resource is attached normally. A global
configuration change is broad only when the affected value was observed broadly.

### 4. Semantic analysis facts

Model SQL analysis remains keyed by expanded SQL, analysis profile, referenced relation interfaces,
binding schema, and engine versions. The persistent representation should retain compact interned
facts so warm reads do not reconstruct duplicate lineage objects entry by entry.

Each model publishes a deterministic interface signature containing the output columns, types,
nullability, wildcard status, and any other fact consumed by downstream analysis. A changed model
invalidates downstream semantic analysis only when this exported interface changes. Its own compiled
artifact still changes whenever its implementation changes.

For supported, schema-bound queries, the native compiler derives immutable CTE output facts from
one parsed query tree. It retains every projection position, including unnamed expressions used by
CTE column lists and positional unions. Known input columns take precedence over same-named SELECT
aliases. Queries with incomplete facts, unsupported source shapes, or unresolved types retain the
existing analysis path. Changes to this inference algorithm invalidate prior analysis identities.

Compiler-expanded SQL and its source-location spans are also reused within one invocation. SQL lint
may start after attachment while semantic analysis continues. Compiler-proven dynamic-output paths
are checked again with their completed proof. Native and custom rules can execute concurrently;
their combined findings pass through the same final exception and suppression policy. These
invocation-local objects and workers are not persisted in the compiler cache.

### 5. Shared derived indexes

Project-wide indexes are built once per compile and shared by all consumers. They include model
dependencies, test model closures, declaration visibility, selector indexes, and artifact identities.
No per-test, per-rule, or per-artifact path may rebuild an unchanged whole-project index.

### 6. Command snapshots

A command snapshot records validated, non-executable output facts after all lower layers complete.
It may provide a no-op fast path only when every input observed by that command is represented in
the snapshot identity. Commands involving untracked runtime values bypass this layer while still
using safe lower-layer facts.

## Invalidation

Invalidation follows recorded dependency edges rather than directory-wide guesses:

1. Compare the current inventory with the last committed inventory.
2. Invalidate directly changed static facts.
3. Follow declaration, macro, configuration, schema, hook, and test dependency edges.
4. Reattach directly affected resources.
5. Reanalyze changed models and compare exported interface signatures.
6. Reanalyze downstream models only when a consumed interface changed.
7. Rebuild tests, audits, rules, and artifacts only when their recorded inputs changed.

Removing an edge is itself an invalidating change. Cache readers must not infer validity from the
absence of a newly introduced dependency record.

## Storage and publication

- Records are schema-versioned and include algorithm and package fingerprints.
- Payloads have explicit size and collection-count limits before semantic acceptance.
- Digests cover keys and canonical serialized payloads.
- Writers publish in one transaction or by atomic replacement; readers observe one committed
  generation.
- Concurrent lock or I/O failure is a cache miss, never a compile failure.
- Cache growth is bounded by generation and byte limits. Pruning removes old immutable records and
  does not mutate current semantic state.
- `--no-cache`, target configuration, and the compile-cache environment override bypass every
  persistent layer and do not publish new records.

## Observability and guards

The target machine-readable contract reports per-layer hits, misses, invalidations, bytes read and
written, and phase timings. The current vertical slice reports model-analysis batch hits, entry
hits, misses, bypasses, and phase timings. Counts describe semantic records, not low-level database
operations.

Concurrent phase timings can overlap. Use the total compile time and fresh-process wall time for
end-to-end comparisons rather than summing individual phase durations.

Fresh-process performance guards use representative semantic projects and cover:

- cold compile with a clean target;
- unchanged warm compile;
- leaf-model implementation edit;
- upstream implementation edit with an unchanged interface;
- interface-changing upstream edit;
- test-only and macro edits;
- broad project-configuration edit;
- cache corruption and `--no-cache` fallback.

Every path verifies exact resource counts, zero unexpected diagnostics, deterministic semantic
fingerprints, bounded peak RSS, and expected hit and invalidation counts. Wall-time ceilings are
calibrated only after the behavior and identity assertions are stable.
