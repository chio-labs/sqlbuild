# Compiler differential

`make compiler-differential` compiles fixtures, examples, generated seeds and the failure corpus
under two compiler engines and fails on the first differing artifact. `make
compiler-differential-shipped` does the same for the shipped `native` default. Both also enforce
the shared gates below.

For ad hoc runs (one project, other seeds, other engines), call the script directly, for example
`uv run python -m scripts.run_compiler_differential --corpus --project <dir> --engines python
native`. The make targets fix the corpus the allow-list and goldens are recorded for.

## Shared gates for native ports

A port that moves work from the Python compiler to native code reuses these three mechanisms. It
does not add its own parity harness, property suite or E2E file.

### Native-to-Python fallbacks and analysis deferrals

`native_fallbacks.toml` is the one allow-list of all work native code still hands back to Python,
and of the work each native stage answers itself. It covers three kinds of record:
- fallbacks, from `report_native_fallback(site=NativeFallbackSite.<SITE>, kind=...)` on every
  path where a native stage hands work to Python, or runs Python with no native path yet;
- preview analysis-stage deferrals: every `analysis-deferrals-*.jsonl` record (analysis session,
  lineage, semantic checks, contracts);
- native answers, from `report_native_answer(stage=NativeStage.<STAGE>, kind=...)` where a
  stage's native path produced the result: files, models, scans or calls. Their site is
  `<stage>.native`.

Counting only fallbacks cannot tell a stage that answers natively from one that no longer runs
natively at all. The answer counts can: if a stage is switched to Python, its `<stage>.native`
entries vanish and the gate says so.

Every entry names an engine, stage, site and kind, with its exact count per corpus. Use
`max_counts` instead of `counts` only for a count that is not stable, and give the reason in a
comment and in the PR body.

The records cost nothing unless `SQLBUILD_ANALYSIS_RECORD_DIR` is set, which only the harness
sets. `--native-fallbacks check` runs in both make targets and fails CI in both directions:
- an entry, engine or corpus count that is not on the list fails;
- a listed entry whose count changed or that no longer occurs also fails, and the message says to
  update or remove it, so the fallback list only shrinks;
- a vanished native answer fails as work that now runs in Python;
- a listed fallback that vanished is refused outright, with "fallback disappeared but native
  answers did not appear; the stage may be switched off", unless the same engine, stage and
  corpus report more `<stage>.native` answers than the list records. A stage with only fallback
  entries (`sql_test_glue`, `project_assembly`) would otherwise look like a finished port when it
  is switched off.

The counts hold for the make targets' corpus (`--seeds 12`); other seed ranges are refused.

Two stages the list cannot watch:
- `type_system`: the compile corpus never reaches type normalization. Its callers are the planner
  and executor and the preview stages' Python fallbacks. `tests/integration/.../type_system/
  test_native_type_parity.py` proves instead that the public `normalize_type` asks native first
  under `native-preview`.
- `discovery.native model_file_listings`: it is reported unconditionally inside the native model
  file discovery, which has no fallback to Python, so this count cannot detect anything. It stays
  only as a record that native discovery ran.

**How a PR updates the list and the goldens**

One command rewrites both from the current tree:

```sh
make compiler-baselines
```

It deletes `tests/goldens/compiler`, then runs the two CI differentials with `--native-fallbacks
update --goldens update`. Commit the resulting `native_fallbacks.toml` and `tests/goldens/` diff
in the same PR as the change that caused it.

- A port deletes the Python code it replaces in the same PR. Its fallback entries then disappear
  from the list, and that removal is the port's test that the fallbacks are gone. Its answer
  counts usually rise. When the last entry for a `NativeFallbackSite` goes, delete the member
  and its `report_native_fallback` call too.
- If the corpus does not reach a site yet, first add a failure case or seed feature that does.
- A PR that merges after a list or golden change on main reruns `make compiler-baselines` after
  rebasing and commits the result.

**What a reviewer checks in the diff**

- `native_fallbacks.toml`:
  - Removed fallback entries and lower fallback counts are expected from ports.
  - Every added fallback entry, higher fallback count or new `max_counts` needs a stated reason
    in the PR body. Never add one just to make CI pass.
  - A removed or lower `<stage>.native` answer count means less native work. It needs a reason
    in the PR body.
  - A removed fallback entry needs new or higher `<stage>.native` answers for the same stage in the
    same diff: the port must report the work it now answers. A fallback that vanished with no new
    answers is a stage switched off, not a port; the gate refuses it.
- Code: every new path that hands work to Python calls `report_native_fallback`, and every new
  native path calls `report_native_answer` where its result is used.
- Goldens:
  - Every changed golden is an intended output change, named in the PR body.
  - An output-neutral port changes no golden.
  - New goldens belong to new corpus cases.
- Proof by sabotage: `test_native_fallback_gate.py` proves the gate by sabotage, so forcing a
  native stage to defer everything must fail it. A new "native did the work" gate needs the same
  proof.

### Golden outputs

`tests/goldens/compiler/<corpus>/<project>.json` holds one project's compile outputs:
- each command's exit code and diagnostics;
- the compiled SQL, one array item per line;
- the manifest without its volatile metadata and the SQL it repeats.

The project directory is masked as `<project>` and the harness work directory as `<work>`,
whether or not the path is resolved. The SQLBuild version, invocation ids and timings are also
masked.

Goldens hold outputs only, not stage captures: a seed's captures are about 690 KB, too large to
review. Cache facts are covered by the incremental-versus-no-cache tests instead.

- `--goldens check` (in both make targets) compares every engine with the goldens, so an
  output-neutral port needs no new parity suite.
- `make compiler-baselines` rewrites them from the python oracle. Run it only when output
  changes on purpose, and review the diff like code.
- `tests/goldens/compiler/seed_range.toml` records the seed range the goldens were written for.
  Every seed in that range, and every fixture, example and failure case, must have a golden.
  Seeds outside the range (ad hoc runs with more seeds) are skipped. A missing `seed_range.toml`
  fails the check for every seed project rather than skipping them.
- Dialect variants (`<seed>-postgres`, `<seed>-snowflake`) are generated for the first seed of a
  run only, so a golden is required only for the variants of the recorded `seed_start`. An ad hoc
  `--seed-start N` run checks its base seeds in the range and skips its variants.
- Once the Python stages are deleted, goldens are rewritten from `native`.

### All-engine user-facing errors

`engine_error_cases()` in `_helpers/corpus/failure_cases.py` lists user-facing errors with their
exact text. Each case is part of the failure corpus, so it runs in both differentials and has a
golden. It also runs in
`tests/e2e/scripts/compiler_differential/test_engine_error_cases.py` on the `python`, `native`
and `native-preview` engines, which must all report its `expected_code` and `expected_message`.

A port that adds or changes a user-facing error adds one `failure_case(...)` to it:

```python
failure_case(
    name="engine-error-<what-goes-wrong>",
    expected_code="P001",
    files=mart_body_files("SELECT ...\n"),
    expected_message="<the exact message, with <project> for the project path>",
)
```

Then it runs `make compiler-baselines` to record the new case's golden.
