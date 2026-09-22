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
| 1,000 | 13s | 2GiB |
| 3,000 | 36s | 3.5GiB |
| 5,000 | 65s | 4GiB |
| 10,000 | 135s | 4GiB |

CI additionally runs each size in a 4GiB cgroup with swap disabled, covering
the test harness and child processes together. Compiler, lint and rule-engine
changes select these jobs. Local process RSS measurements alone do not prove
the cgroup gate passes.

Run an individual size with:

```sh
make test-e2e-dense-compile-performance SQLBUILD_BENCHMARK_MODELS=1000
```

For requests containing at least 32MiB of unique SQL, the compiler compacts native
analysis results in batches of 64 and uses at most two workers to bound
simultaneous parser heaps. Smaller requests retain a single batch and up to four workers.
These limits change scheduling, not analysis or fallback semantics.

This fixture protects dense query analysis, declaration expansion, rules and
artifact generation. It is not an exact reproduction of every application:
dynamic plugins, incremental materialization mixes and deeply nested query
tails still require application-specific acceptance measurements. Keep those
measurements private; publish only neutral fixtures and their own results.
