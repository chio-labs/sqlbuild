<!-- generated-by: sqlbuild skills -->

# Benchmarks

> Complete compiler performance on projects with thousands of models, SQL tests, and audit attachments.

Online: https://docs.sqlbuild.com/benchmarks

## Contents

- Compiler performance
- Rules performance
- Methodology
- Reproduce the benchmarks

SQLBuild compiles a 5,000-model project with nearly 5,000 SQL tests and more than 8,000 audit
attachments from scratch in **19 seconds** in our CI benchmark. An unchanged recompile takes
**13 seconds**.

These measurements run the complete `sqb compile` command, including project discovery, dependency
resolution, SQL expansion and analysis, contract validation, test and audit preparation, configured
Rules, cache publication, and artifact generation.

## Compiler performance

| Compile time | **3k models**<br />2.9k tests · 5.1k audit attachments | **5k models**<br />4.9k tests · 8.4k audit attachments |
|---|---:|---:|
| First compile / cache fill | **12.48s** | **19.01s** |
| Unchanged recompile | **8.79s** | **12.76s** |

Timings include test and audit preparation, not warehouse execution.

The 5,000-model compiler process used approximately **1.3 GiB peak resident memory** on its first
compile and **0.7 GiB** on its unchanged recompile.

### Workload details

The deterministic generated projects exercise compiler work at scale, with synthetic SQL,
contracts, macros, functions, tests, and audits.

| Resource | 3k-model project | 5k-model project |
|---|---:|---:|
| Models | 3,000 | 5,000 |
| Sources | 713 | 1,189 |
| Seeds | 141 | 236 |
| SQL functions | 71 | 118 |
| Python macros | 37 | 61 |
| SQL test cases | 2,945 | 4,908 |
| Audit attachments | 5,056 | 8,427 |

The projects use repeated generated structures. Individual project timings depend on SQL
complexity, macros, configuration, and hardware as well as model count.

### Incremental compilation

SQLBuild reuses cached analysis for unaffected models. In the 5,000-model benchmark, a single-model
file edit reused **4,999 model analyses**. A scoped Python-macro edit required fresh analysis for
**7 models**. Both scenarios completed in approximately **9.8 seconds**.

The single-model scenario appends a SQL comment to exercise file-change invalidation. Separate
regression coverage checks expression-changing edits against uncached compilation results.
Scenarios run in a fixed sequence and use different cache-loading paths; an edit timing below the
initial unchanged timing does not mean editing inherently requires less work.

## Rules performance

Rules participate in ordinary compilation. Model Rules are cached per model, and SQLBuild tracks
their dependencies so unaffected findings can be reused after edits. Project Rules evaluate the
complete project view and have broader invalidation.

A separate custom-Rules benchmark exercises 20- and 100-Rule packs over 5,000 models. It measures
first compilation, unchanged compilation, model edits, and Rule implementation changes. This is a
different workload from the compiler table above; its results should be compared within that profile.

See [Execution and caching](concepts/rules/execution-and-caching.md) for the Rules lifecycle, or run
the publication profile below to collect current custom-Rules measurements.

## Methodology

The compiler results above are individual scenario measurements from the
[passing CI run on September 22, 2026](https://github.com/chio-labs/sqlbuild/actions/runs/35764207007),
using the compiler code released in **SQLBuild 0.113.3** and Python 3.12 on Linux. They are not
multi-run medians.

Each scenario launches a fresh process. The first compile starts with an empty project cache;
subsequent scenarios reuse that cache. The CI job enforces a **4 GiB combined memory limit**.
Reported peak resident memory is for the compiler process, not the entire CI job.

CI checks cache-hit and miss expectations and pinned semantic fingerprints alongside timing and
memory budgets. The varied 1,000-model guard additionally compares SQL-expression and macro edits
with uncached analysis and Rules results.

These measurements cover compilation and static analysis. SQL tests and audits are prepared, not
executed against a warehouse.

## Reproduce the benchmarks

Run the fresh-process compiler cache guards from the
[SQLBuild repository](https://github.com/chio-labs/sqlbuild):

```bash
make test-e2e-cache-compile-performance SQLBUILD_BENCHMARK_MODELS=3000
make test-e2e-cache-compile-performance SQLBUILD_BENCHMARK_MODELS=5000
```

Run the five-iteration custom-Rules publication profile:

```bash
uv run python -m scripts.benchmark_rules \
  --models 5000 \
  --rule-counts 20 100 \
  --iterations 5 \
  --output rules-5000.json
```

Run the bounded Rules profile used by required CI:

```bash
uv run python -m scripts.benchmark_rules_ci \
  --output rules-performance-ci.json \
  --summary-output rules-performance-ci.md
```

The benchmark generators, guard thresholds, and CI workflow are maintained in the public
[SQLBuild repository](https://github.com/chio-labs/sqlbuild).
