# Dense all-rules compile guard

The dense compile guard covers cold compilation of 1,000, 3,000, 5,000 and
10,000 models with every built-in compiler rule and one custom project rule
enabled. It complements the existing semantic and incremental-cache benchmarks.

The deterministic fixture uses neutral order data and compiles offline with the
Snowflake dialect. Each 1,000-model group has 240 sources, 50 seeds, 25 SQL
functions, 1,700 audits and 1,000 SQL tests. Queries contain dependency import
CTEs, joins, named unions, explicit contracts, wide projections and Python macro
expansion. Independent declaration scopes preserve per-model macro visibility
as the project grows. SQL tests mock immediate inputs to keep test expansion
bounded. A smaller integration fixture executes its generated tests in DuckDB.

The guard checks:

- Complete built-in rule selection, one selected custom rule, and no ignored
  rules, scoped exceptions or relaxed thresholds.
- Resource counts, minimum authored SQL volume, and zero diagnostics.
- Zero analysis/rule cache hits and analysis bypasses for every model.
- A fingerprint of semantic JSON and every compiled artifact.
- Fresh-process wall time and peak RSS, with phase timings in test logs.

| Models | Wall-time ceiling | Process RSS ceiling |
| ---: | ---: | ---: |
| 1,000 | 14s | 1.5GiB |
| 3,000 | 34s | 2.75GiB |
| 5,000 | 55s | 3.25GiB |
| 10,000 | 145s | 4GiB |

These are regression ceilings for the implemented compiler, with headroom for
host variation. They are not a claim of sub-10-second compilation at every size.

CI additionally runs each size in a 4GiB cgroup with swap disabled, covering
the test harness and child processes together. Compiler, lint and rule-engine
changes select these jobs. Local process RSS measurements alone do not prove
the cgroup gate passes.

Run an individual size with:

```sh
make test-e2e-dense-compile-performance SQLBUILD_BENCHMARK_MODELS=1000
```

For requests containing at least 32MiB of unique SQL, the compiler compacts native
analysis results in batches of 64. Smaller requests retain a single batch. Both
use up to four workers; local resolution views avoid copying CTE definitions
that are already available through the source catalogue.
These limits change scheduling, not analysis or fallback semantics.
Projects with at least 10,000 model projections and 48MiB of prepared SQL use one
native analysis worker to leave memory headroom for the isolated custom-rule host
after analysis. Smaller SQL payloads retain parallel analysis.
The 10k cold ceiling includes headroom for this memory-bounded scheduling; warm
cache hits and small edit batches keep their existing scheduling.

The compiler reuses borrowed syntax-tree facts when it can prove complete reference
binding and infer types without consulting mutable type annotations. Unsupported
clauses, incomplete schemas and unresolved expressions retain the normal validation
and analysis paths.

For cold projects with 128–5,000 models and selected rules, artifact rendering can overlap rule
evaluation after graph and contract analysis. Rendering uses one background thread
and a disposable directory outside the project. The normal write phase publishes
the staged files only after its existing diagnostic gates pass. Unchanged files
retain their timestamps, stale files are removed using the normal policy, and
cached compilation keeps its normal artifact-cache path. Temporary-storage failure
falls back to ordinary artifact writing.
Larger projects retain sequential rendering to bound combined compiler and rule-host
memory; projects without selected rules avoid staging's extra file I/O.

Detailed phase timings can overlap; physical-write time includes any staging work.
Use whole-process wall time for performance acceptance rather than summing phases.
Custom rules continue to run in their isolated host. Disabled rules caches avoid
unused fact fingerprints; enabled caches retain their normal identities and
invalidation behavior.

The [varied warm-compile guard](warm-compile-performance.md) adds operator-shape
diversity and a shared dependency graph, measuring unchanged, leaf, upstream and
macro-edit compiles against uncached semantic/artifact oracles.

This fixture protects dense query analysis, declaration expansion, rules and
artifact generation. It is not an exact reproduction of every application:
dynamic plugins, incremental materialization mixes and deeply nested query
tails still require application-specific acceptance measurements. Keep those
measurements private; publish only neutral fixtures and their own results.
