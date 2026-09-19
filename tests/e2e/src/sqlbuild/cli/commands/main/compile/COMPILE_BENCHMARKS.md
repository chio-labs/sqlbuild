# Compile performance benchmarks

SQLBuild maintains complementary generated projects because model count alone does not predict
compile cost. Every fixture uses neutral orders-style names and synthetic SQL.

## Layered scale guard

The layered guard combines 976 models, 232 sources, 46 seeds, 23 SQL functions, 700 attached
audits, 130 native tests, two hooks, and 54 execution layers. Its model files follow a bounded SQL
size distribution up to roughly 520 KB. The graph contains a 54-layer spine and independent
eight-model chains.

This guard measures cold, unchanged, leaf-model edit, central-model edit, test edit, macro edit,
and project-config edit paths. It protects mixed-resource scaling and cache invalidation while the
separate 3,000/10,000-model and test-heavy guards retain their narrower contracts.

Budgets:

- cold compile: under 7 seconds;
- unchanged warm compile: under 3 seconds;
- one-model, one-test, and one-macro edits: under 4 seconds;
- project-config edit: under 8 seconds.

## Semantic density guard

The semantic guard exercises costs that SQL-size padding cannot represent:

| Characteristic | Generated guard |
| --- | ---: |
| Models | 976 |
| Sources | 232 |
| Seeds | 46 |
| SQL functions | 23 |
| Attached audits | 1,645 |
| Native test cases | 958 |
| Declared model columns | about 33,000 |
| Model SQL | about 5.8 MB |
| Compiled test SQL | about 13 MB |
| Hooks | 2 |
| Execution layers | 54 |

Declared column widths range from three to 538 columns. The SQL uses real expression trees rather
than comment-only padding: casts, conditional expressions, CTEs, derived tables, macros, functions,
seed joins, assertions, and a 267-branch set operation feeding a 270-column aggregate. The large set
operation specifically protects schema validation and CTE type inference from nested-tree
materialization regressions.

The guard records phase timings for cold and unchanged warm compiles. It enforces a 60-second cold
budget and a 12-second warm budget. Resource counts, declared-column count, model SQL bytes, and
compiled-test bytes are asserted so simplifying the fixture cannot make the performance check pass.

Both guards initialize the process-local SQL runtime with an unrelated 32-model project before
measurement. “Cold” means the measured project has no compiler cache or target artifacts; it does
not include one-time lazy initialization noise from the Python test worker. Phase timings are
attribution spans rather than additive buckets.
