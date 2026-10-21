# SQLBuild vs dbt: dense project compile benchmark

This harness generates one dense synthetic project in both SQLBuild and dbt form, then times the
same edit loop in each tool. It compares SQLBuild with dbt v2 (the `dbt` package on PyPI), with
dbt Core as a reference. Published results are on the
[Benchmarks](https://sqlbuild.com/docs/benchmarks) page.

## Files

| File | Purpose |
|---|---|
| `write_dbt_dense.py` | Writes `sqlbuild/`, `sqlbuild-norules/`, `dbt/`, `warehouse.duckdb` and `profiles/` for N models |
| `edit_models.py` | Changes one constant in the SQL body of N evenly spaced models, in either project |
| `bench.sh` | Times cold, warm, one-model edit and 100-model edit runs per variant, in alternating order |
| `summarize.py` | Prints median wall time, CPU time and peak RSS per variant and scenario |
| `correctness.sh` | Runs every tool on 50-model projects: clean, a missing `ref`, and a missing column |

## The project

`write_dbt_dense.py` imports the dense generator used by the compile-performance CI jobs
(`scripts/cold_compile_performance/_helpers/dense_project.py`) and switches its adapter to DuckDB.
Nothing else in the SQLBuild project changes. The dbt project is derived from it file by file, so
model names, folders, SQL bodies and the DAG are the same.

At 10,000 models the project has 2,400 sources, 500 seeds, 250 SQL functions, 120 macros,
17,000 `not_null` checks and 10,000 SQL tests. Models are wide: 8 to 472 columns, about 31 on
average.

| SQLBuild | dbt |
|---|---|
| `MODEL (...)` header with typed columns | `_models.yml` per folder, `data_type`, `contract: {enforced: true}` |
| `__ref`, `__source`, `__udf` | `ref`, `source`, `function` |
| Python macros | Jinja macros producing the same SQL |
| `audits [not_null]` | `data_tests: [not_null]` |
| SQL tests with fixture CTEs | `unit_tests` with the same input and expected rows |
| `[rules] select = ["SQBR", "XSQBR"]` (built-in Rules plus one custom Rule) | none |

`sqlbuild-norules/` is the same project with `[rules] select = []`. That turns off configurable Rules;
column binding, type inference and contract checks still run.

## Running it on GitHub Actions

The `Benchmark dbt comparison` workflow (`.github/workflows/benchmark-dbt.yml`) runs only when
started by hand. It installs the requested released versions from PyPI, runs `correctness.sh`, then
`bench.sh`, and uploads the results directory with a `summary.md` (environment, correctness table,
benchmark table). The same summary appears on the run page.

```bash
gh workflow run benchmark-dbt.yml -f sqlbuild_version=0.164.2 -f rounds=3
```

| Input | Default |
|---|---|
| `sqlbuild_version` | empty: the latest release |
| `dbt_version` | `2.0.9` |
| `dbt_core_version` | `1.12.6` |
| `dbt_duckdb_version` | `1.11.0` |
| `models` | `10000` |
| `rounds` | `3` |
| `variants` | all eight variants below |

## Running it locally

Use the released packages in fresh virtual environments. From the repository root:

```bash
uv venv -p 3.12 /path/to/venv-sqb && uv pip install -p /path/to/venv-sqb/bin/python sqlbuild pytest duckdb
uv venv -p 3.12 /path/to/venv-dbt2 && uv pip install -p /path/to/venv-dbt2/bin/python dbt
uv venv -p 3.12 /path/to/venv-dbt && uv pip install -p /path/to/venv-dbt/bin/python dbt-core dbt-duckdb

export SQB=/path/to/venv-sqb/bin/sqb DBT_V2=/path/to/venv-dbt2/bin/dbt \
  DBT_CORE=/path/to/venv-dbt/bin/dbt PYTHON=/path/to/venv-sqb/bin/python

"$PYTHON" benchmarks/dbt-compare/write_dbt_dense.py --models 10000 --out /path/to/p10k
benchmarks/dbt-compare/correctness.sh /path/to/correctness
benchmarks/dbt-compare/bench.sh /path/to/p10k /path/to/results 3
python3 benchmarks/dbt-compare/summarize.py /path/to/results
```

The generator imports the CI helpers from the checkout, so it needs a Python with `sqlbuild`,
`duckdb` and `pytest` installed, and works best with a sqlbuild release close to the checkout.
Nothing is built from source. Run on an otherwise idle machine: other load changes wall times far
more than CPU times.

## What each run does

For every variant and round, `bench.sh` copies the pristine project into `work/VARIANT`, waits
five seconds, then runs:

1. **cold**: the command with no `target/` and no caches.
2. **warm**: the same command again with nothing changed.
3. **edit1**: one model's SQL body edited, then the command.
4. **edit100**: 100 models' SQL bodies edited (1% of 10,000), then the command.

Each edit changes one constant in a projection, so the query changes but its columns, types and
references don't. Rounds alternate the variant order. `SCENARIOS` limits which of warm, edit1 and
edit100 run.

Commands, run from the project copy:

| Variant | Command |
|---|---|
| `sqb_rules` | `sqb --no-color compile` in `sqlbuild/` |
| `sqb_norules` | `sqb --no-color compile` in `sqlbuild-norules/` |
| `sqb_rules_full` | `sqb_rules` with `SQLBUILD_DISABLE_COMPILE_REUSE=1 SQLBUILD_DISABLE_DELTA_COMPILE=1`: every run is a full compile that uses the per-model caches |
| `v2_parse` / `v2_compile` | dbt v2 `parse` / `compile` with `--profiles-dir ../profiles --no-version-check` |
| `v2_compile_strict` | dbt v2 `compile --static-analysis strict`, which checks columns like SQLBuild does |
| `core_parse` / `core_compile` | the same `parse` / `compile` commands with dbt Core |

Both tools use their defaults otherwise: SQLBuild's compile cache, reuse and delta compile, and
dbt's partial parsing. `DBT_SEND_ANONYMOUS_USAGE_STATS=false` is set. The DuckDB profile sets
`threads: 4`.

`/usr/bin/time -f '%e %U %S %M'` records wall time, user and system CPU, and the peak RSS of the
largest process. `summarize.py` also reports what each tool said it did: SQLBuild prints whether it
reused the previous compile or compiled only the changed files, and dbt Core logs when it falls back
to a full parse. The 1-minute load average before and after each run is recorded too.

## What isn't equivalent

- SQLBuild compile binds every column, infers types and checks contracts. dbt v2 does this with
  `--static-analysis strict`; its default compile doesn't report unknown columns. dbt Core compile
  renders Jinja and resolves references without analysing the SQL.
- SQLBuild compile also runs configurable Rules (`sqb_rules`). dbt has no built-in counterpart.
- SQLBuild compile prepares its 10,000 SQL tests. dbt `compile` parses the unit tests but doesn't
  render them; that happens in `dbt test` or `dbt build`.
- dbt renders every model through Jinja; SQLBuild expands references and macros in its own compiler.
  That cost is part of each tool and is included.
