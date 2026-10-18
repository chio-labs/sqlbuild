# sqlbuild vs dbt v2: dense 10k project, cold compile (PRIVATE)

Date: 2026-10-18. Host: 4-core Intel i5-7600 @ 3.5 GHz, 62 GiB RAM, Linux 6.11. This is a shared
machine; every run held `/mnt/data/.native-build.lock`.

## Versions

| Tool | Version | How it was obtained |
|---|---|---|
| sqlbuild | 0.156.1 (`/mnt/data/sqlbuild-perf1/.venv/bin/sqlbuild-python`, used read-only) | existing venv |
| dbt (full distribution, formerly Fusion) | `dbt 2.0.8` | `uv venv venv-dbt && uv pip install dbt` (PyPI wheel, Python 3.14.7, 400 MB `_core.abi3.so`) |
| dbt-oss (Apache 2.0 runtime) | `dbt-oss 2.0.8` | `uv venv venv-dbt-oss && uv pip install dbt-oss` (217 MB `_core.abi3.so`) |
| DuckDB ADBC driver | `libadbc_driver_duckdb-1.5.4.so` | already in `~/.cache/com.getdbt/adbc/` from June. No download happened during these runs |
| DuckDB (to create the source DB) | python duckdb 1.5.2 | sqlbuild-perf1 venv, used read-only |

I didn't build from source: both pip packages installed, so `/mnt/data/dbt-compare-target` was never
created and `~/git_repos/dbt-core` wasn't touched. I didn't download Fusion separately,
because the `dbt` wheel is that distribution. I never ran `dbt login`. `dbt license info` reports
`status: not_found, licensing_enabled: true`. On first run dbt created `~/.dbt/leases/`, which is empty.

## Files

- `write_dbt_dense.py --models N --out DIR [--seed-error]` imports the unchanged sqlbuild dense generator
  and writes `sqb-duck/` (adapter switched to `duckdb`; nothing else changed. At 10k its `models/` is
  byte-identical to `/mnt/data/perf10k/var-full`), `sqb-duck-norules/`, `dbt/` (derived file by file
  from `sqb-duck`), `warehouse.duckdb` and `profiles/profiles.yml` (`type: duckdb`, absolute path,
  `schema: analytics`, `threads: 4`).
- `correctness.sh`: the 50-model clean and seeded-error matrix. Logs are in `correctness/`.
- `bench.sh ROUNDS OUTDIR`: cold benchmark. Raw results are in `bench10k/` (`*.time`, `*.out`, `*.err`,
  `uptime.log`, `summary.log`), and `warmup/` holds the untimed warm-up round.
- `summarize.py`: the median table. `diag.sh` / `diag/`: a one-off run with the unit-test YAML removed.

No sqlbuild-specific syntax needed changing for DuckDB. `UNION ALL BY NAME`, `INTEGER` and `DOUBLE` are
valid there, and every tool accepted the SQL: parse and compile were clean on both sides, apart from
dbt lint style warnings.

## Feature mapping

| sqlbuild construct | dbt v2 equivalent | Notes |
|---|---|---|
| Model file + `MODEL (...)` header | `.sql` file + one `_models.yml` per `batchNNNNN/` folder (5 models each) | Same names, folders and DAG |
| `__ref("m")` / `__source("orders_N")` | `{{ ref('m') }}` / `{{ source('raw','orders_N') }}` | Sources live in one dbt source `raw` (database `warehouse`, schema `raw`) |
| `materialized table`, `description` | `config.materialized: table`, `description` | |
| `contract enforced`, column `type` | `contract: {enforced: true}`, `data_type` | |
| `nullable false` | `constraints: [{type: not_null}]` | |
| `audits [not_null]` (17,000) | `data_tests: [not_null]` (17,000) | |
| Source YAML with typed columns + `expression` | dbt sources YAML with `data_type`, plus real empty tables in `warehouse.duckdb` | The sqlbuild `expression` is kept; dbt has no such concept |
| Seeds (500 CSV + types) | Same CSVs, `config.column_types: {id: integer, label: varchar}` | Column `data_type` dropped because dbt warned that its inferred `character varying(256)` overrides `varchar` |
| Python macros (`@macro_CCC_NNNNN("expr")`, with a composed `base_offset_CCC`) | Jinja macros `{{ macro_CCC_NNNNN("expr") }}`, with the composition kept (`macro_*_00000` calls `base_offset_*`) | Rendered SQL is identical: `((b.id + 0) + 1)` |
| SQL functions (`__udf("fn_N")(x)`, 250) | dbt v2 `functions/` UDF resources + `{{ function('fn_N') }}(x)` | Parsed and compiled as `function` nodes |
| SQL tests with fixture CTEs (10,000) | dbt `unit_tests` (10,000), one `given` per mocked ref/source with the same rows, `expect` with the same row | Not semantically identical: dbt unit tests run only in `dbt test`/`build`. `compile` parses them but doesn't plan or execute them, and isn't asked to |
| `[rules] select = ["SQBR","XSQBR"]`: 84 built-in rules plus the custom `XSQBRBENCH001` | `dbt lint` (SQLFluff defaults, `dialect = duckdb`, `templater = dbt`) + 3 `checks/` | Not equivalent; see below |
| Custom-rule pytest file `tests/test_rule_contracts.py` | not mapped | No dbt equivalent |

### Rules vs dbt lint and checks (these are not equivalent)

- **sqlbuild `sqb-duck`** runs 84 built-in rules (CONTRACT 6, DECLARATION 9, GRAPH 2, MODEL 4,
  PROJECT 10, SQL 45, TEST 8; see `sqb-rules-list.txt`) plus the Python custom rule `XSQBRBENCH001`
  ("order contracts must be present"). These are compiler-integrated and see the resolved graph,
  lineage and contracts. To turn them off, `sqb-duck-norules` sets `[rules] select = []`; the
  documented behaviour is that "an empty select disables configurable Rules. It does not disable
  mandatory compiler correctness". There's no CLI flag for this. With `select = []`,
  `built_in_rules_ms` and `custom_rules_ms` are both 0, and column binding still runs.
- **`dbt lint`** (full distribution only; dbt-oss says "requires the full dbt distribution") is a
  SQLFluff-compatible linter over rendered SQL. I used the default rule set. The `jinja` templater is
  rejected with "only supports SQLFluff templater 'dbt'", so the config uses `dbt`. On this project
  only `ST09` fired (17,200 warnings at 10k, 90 at 50). It checks style only: no lineage, contracts or
  graph.
- **`dbt check`** (it works in both dbt and dbt-oss) runs SQL against parse-time `info_schema()` views.
  It needs `info_schema: {version: 1}` in `dbt_project.yml`. I wrote 3 checks:
  `models_have_enforced_contract` (the counterpart of `XSQBRBENCH001`, and close to `SQBRCONTRACT101`),
  `models_have_description`, and `model_columns_have_data_type` (close to `SQBRCONTRACT106`). All 3
  pass on the generated project. I confirmed they work with a negative test (remove the description,
  contract and one `data_type` from one model): 3 failures, exit 1. They cover metadata only, with no
  SQL semantics, so they cover a small subset of what sqlbuild's rules check.

## Correctness (50 models, `correctness/`)

The seeded error: model `sales000__int_clean__orders_00002` selects `COALESCE(b.missing_col, 0)`, where
`b` is `ref('…_00001')`, which has no such column. The edit is applied identically in all three projects.

| Tool / mode | Clean project | Seeded column error |
|---|---|---|
| sqlbuild compile (rules) | rc 0, 0 diagnostics | **rc 1, `B002 Unknown column 'missing_col' in b`** |
| sqlbuild compile (`select = []`) | rc 0 | **rc 1, same B002** (binding is mandatory, not a rule) |
| dbt 2.0.8 compile, default (`baseline`) | rc 0 | rc 0, **nothing reported** |
| dbt 2.0.8 compile `--static-analysis strict` | rc 0 ("downloading schemas (12 items)" from the local DuckDB) | **rc 1, `[error] UnresolvedIdentifier (dbt0227): No column b.missing_col found. Available are b.amount, l0.amount, b.id, …`**. 124 downstream nodes skipped |
| dbt 2.0.8 compile `--static-analysis off` | rc 0 | rc 0, nothing |
| dbt-oss 2.0.8 compile default / `baseline` / `off` | rc 0 | rc 0, nothing |
| dbt-oss 2.0.8 compile `--static-analysis strict` | rc 0 + warning | rc 0 + only `[warning] Generic (dbt1000): static analysis was requested with --static-analysis strict but did not run: this distribution of dbt OSS does not include the static analysis engine. Install the full dbt distribution …` |
| `dbt parse` (both) | rc 0 | rc 0. `parse` rejects `--static-analysis` ("unexpected argument", exit 2) |

Extra probe, a syntax error (`SELECT FROM WHERE ,,`): dbt baseline reports
`[warning] SyntaxInvalid (dbt0101)` and exits 0. dbt-oss reports nothing and exits 0. So baseline does
parse SQL but doesn't resolve columns, and dbt-oss has no SQL analysis engine at all.

**Login:** none of these needed `dbt login`: strict static analysis, `lint`, `check` and
schema download all worked unauthenticated on DuckDB. This contradicts the brief's description that
strict needs login and falls back to baseline without it. I saw no fallback message, and strict
caught the error. Login-gated features may differ on other adapters or later versions; I didn't
test that.

## Cold 10k benchmark (`bench10k/`)

Project: 10,000 models, 2,400 sources, 500 seeds, 250 functions, 17,000 not_null tests,
10,000 SQL tests / unit tests. dbt project: 14,878 files (149 MB). sqlbuild project: 20,875 files
(184 MB). Each variant ran 3 times in alternating order (odd rounds forward, even rounds reversed),
after one untimed warm-up round (`warmup/`). Before every run the script deleted `target/`, `logs/`
and `.sqlbuild` for every project, plus dbt `target/`, `logs/`, `dbt_packages`; then `sync`.
Measurements use `/usr/bin/time -f '%e %U %S %M'`. Threads: `SQLBUILD_CONCURRENCY=4`; dbt got
`--threads 4` plus `threads: 4` in the profile. Every dbt run used
`--no-version-check --no-send-anonymous-usage-stats`. All 57 runs exited 0.

Exact commands (P=/mnt/data/meas/dbt-compare/p10k; dbt commands run from `$P/dbt`):

```
sqb_rules    SQLBUILD_CONCURRENCY=4 sqlbuild-python --project-dir $P/sqb-duck --no-color compile --json --no-cache
sqb_norules  SQLBUILD_CONCURRENCY=4 sqlbuild-python --project-dir $P/sqb-duck-norules --no-color compile --json --no-cache
dbt_*        venv-dbt/bin/dbt     <parse|compile|lint|check> --profiles-dir ../profiles --threads 4 --no-version-check --no-send-anonymous-usage-stats [--static-analysis strict|off] [--no-write-json]
oss_*        venv-dbt-oss/bin/dbt <parse|compile|check>      (same flags)
```

| variant | wall s (median) | wall s (3 runs) | user+sys s (median) | peak RSS MiB (median) | 1-min load at start/end of each run (range) |
|---|---|---|---|---|---|
| **sqb_rules** (85 rules) | **25.26** | 26.6, 25.3, 25.2 | 57.1 | 3628 | 3.61–7.34 |
| **sqb_norules** | **18.59** | 19.7, 18.6, 18.4 | 33.5 | 2868 | 2.79–6.42 |
| dbt_parse | 35.05 | 36.0, 34.3, 35.0 | 45.8 | 3922 | 2.79–6.04 |
| dbt_parse_nojson | 32.34 | 32.3, 32.0, 32.4 | 42.9 | 3249 | 2.82–4.11 |
| dbt_compile_baseline (default) | 51.14 | 52.3, 50.3, 51.1 | 93.4 | 5706 | 2.80–4.38 |
| dbt_compile_baseline_nojson | 48.53 | 48.5, 48.1, 48.9 | 90.6 | 5259 | 3.00–4.77 |
| **dbt_compile_strict** (catches the column error) | **85.65** | 85.7, 85.8, 85.2 | 200.7 | 4908 | 3.00–4.77 |
| dbt_compile_strict_nojson | 83.55 | 83.7, 82.3, 83.5 | 199.7 | 4131 | 3.30–4.65 |
| dbt_compile_off | 52.54 | 52.5, 44.3, 52.8 | 73.2 | 5112 | 3.28–4.67 |
| dbt_compile_off_nojson | 44.30 | 46.0, 41.7, 44.3 | 67.9 | 5032 | 3.18–4.67 |
| dbt_lint | 80.10 | 80.1, 79.3, 84.3 | 216.7 | 3394 | 1.87–4.28 |
| dbt_check (3 checks) | 49.06 | 50.0, 49.1, 48.5 | 59.7 | 5247 | 1.87–4.28 |
| oss_parse | 34.84 | 36.0, 34.6, 34.8 | 45.3 | 4023 | 2.18–3.37 |
| oss_parse_nojson | 32.80 | 32.3, 34.5, 32.8 | 43.1 | 3154 | 2.18–3.37 |
| oss_compile_default | 45.02 | 45.0, 48.0, 44.8 | 69.6 | 4977 | 1.96–3.24 |
| oss_compile_default_nojson | 41.49 | 40.8, 44.0, 41.5 | 67.0 | 4648 | 1.95–2.84 |
| oss_compile_strict (falls back, warns) | 45.35 | 45.4, 48.0, 44.9 | 70.4 | 5017 | 1.87–2.52 |
| oss_compile_off | 45.99 | 43.8, 46.0, 48.8 | 70.9 | 5172 | 2.18–2.52 |
| oss_check | 50.05 | 50.0, 47.8, 52.2 | 58.8 | 5225 | 2.25–2.51 |

Like-for-like headline (both detect the seeded column error): sqlbuild compile with rules took
25.3 s; dbt `compile --static-analysis strict` took 85.7 s, about 3.4× slower in wall time and 3.5× more CPU.
The default dbt compile, which doesn't detect it, took 51.1 s. sqlbuild without rules took 18.6 s;
it still binds columns.

Diagnostic (`diag/`, one cold run each, `dbt` with all `_unit_tests.yml` removed, load 3.3–4.4):
`parse` took 32.9 s (user+sys 43.1 s), against a 35.0 s median with the unit tests. So the 10,000 wide
unit tests account for about 2 s of parse, and they don't explain the gap to sqlbuild. `compile` took
63.8 s, which is slower than the 51.1 s median with unit tests. It's a single run on a busy machine
(other builds were queued on the lock), so I treat it as noise, not as a result.

External reference only: dbt's blog cites a 10k-node project compiling in 17 s on v2. That project,
its hardware and its flags are unknown. Our nodes are very wide (about 31 columns on average,
up to 472), and the project carries 1.32M lines of YAML (properties, sources, unit tests).

## Caveats

- **Shared machine, 4 cores.** Other agents' Rust builds that respect the lock ran between my runs,
  and I held the lock for the whole 45-minute run. The 1-min load average in each row includes my own
  previous run decaying (each run is CPU-bound for 20–85 s), so it overstates outside interference.
  The first sqlbuild run started at load 7.34, straight after another build released the lock. Spread
  between runs is under 5% everywhere except `dbt_compile_off`, which has one 44.3 s outlier.
- **Peak RSS** is the `/usr/bin/time` `%M` of the largest process in the tree (wrapped in `bash -c`).
  It is not the sum.
- **Rules have no dbt equivalent.** `dbt lint` covers SQL style and `dbt check` covers metadata. The
  three checks I wrote cover a small subset of sqlbuild's 85 rules. Neither does graph, lineage or
  contract-semantics checks. The lint and check timings are listed for completeness, not as a
  counterpart to `sqb_rules − sqb_norules`.
- **SQL tests vs unit tests.** sqlbuild `compile` compiles and plans its 10,000 SQL tests (`tests:
  10000` in the summary). dbt `compile` parses the 10,000 unit tests but doesn't render or plan them;
  that happens in `dbt test`/`build`. The not_null tests are compiled on both sides (17,000).
- **Jinja cost.** dbt renders every model through Jinja (`ref`, `source`, `function`, macro calls).
  sqlbuild expands `__ref`, `@macro` and `__udf` in its own compiler. This is inherent to each tool and
  is included in the times.
- **dbt-oss has no SQL static analysis.** `baseline` and `strict` don't change its behaviour (strict only
  warns), which is why all oss compile variants take about the same time.
- **Login-gated features:** none were found for this DuckDB workflow. `strict`, `lint` and `check`
  all ran without logging in. The DuckDB adapter is labelled beta. The ADBC DuckDB driver was already
  cached in `~/.cache/com.getdbt/adbc` and I kept it between runs; it's a driver install, not a
  project cache.
- dbt `compile` also writes Parquet metadata under `target/`, even with `--no-write-json`.
  `--no-write-json` saves about 2–8 s.
- The JSON output modes are different: sqlbuild `--json` prints a summary, and dbt prints a text log.
