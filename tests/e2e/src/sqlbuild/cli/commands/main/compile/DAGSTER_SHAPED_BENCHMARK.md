# Dagster-shaped compile benchmark

This generated project protects SQLBuild against regressions that only appear when model,
declaration, native-test, and artifact-writing workloads occur together. It contains no Dagster
SQL, names, or fixture data.

The profile was sampled from the September 2026 Dagster SQLBuild project. Counts and model SQL
sizes are intentionally close, while generated names and logic are generic:

| Characteristic | Dagster profile | Generated guard |
| --- | ---: | ---: |
| Models | 976 | 976 |
| Sources | 232 | 232 |
| Seeds | 46 | 46 |
| SQL functions | 23 | 23 |
| Attached audits | 731 | 700 |
| Native test cases | 130 | 130 |
| Hooks | 2 | 2 |
| Execution layers | 54 | 54 |
| Model SQL bytes | 6.05 MB | about 6.4 MB |
| Model SQL p50 / p75 | 1.9 / 4.5 KB | 1.9 / 4.5 KB |
| Model SQL p90 / p95 | 10.9 / 15.2 KB | 11.0 / 15.2 KB |
| Model SQL p99 / max | 48.2 / 519 KB | 48.0 / 520 KB |

The graph combines one 54-layer spine with bounded eight-model test chains. SQL shapes include
roughly 49 top-level CTE models, 49 derived-table models, and direct selects for the remainder.
It also includes path defaults, a reusable schema, an enforced contract, attached audits, two SQL
hooks, SQL functions, seed and source references, macros (including a composed macro), assertions,
26 repeated test targets, and fixtures ranging from 40 to 200 rows. Generated comments reproduce
the source-size distribution without manufacturing thousands of expensive CASE branches that do
not represent the real project's SQL analysis cost.

The guard measures cold, unchanged, leaf-model edit, central-model edit, test edit, macro edit, and
project-config edit paths. JSON output reports discovery, attachment, model analysis, test input
compilation, test planning, comparison rendering, cache publication, physical writes, and stale
artifact traversal so a failure identifies the regressed phase rather than only the total runtime.
The detailed timings are attribution spans, not additive buckets: attachment includes test-input
compilation and its CTE-cache publication, model analysis includes its cache publication, and the
legacy write span contains test planning, comparison rendering, cache publication, physical writes,
and stale traversal.

The process-local SQL runtime is initialized with an unrelated 32-model project before measuring.
“Cold” therefore means no compiler cache or target artifacts exist for the representative project;
it does not include one-time lazy initialization noise from the Python test worker.
