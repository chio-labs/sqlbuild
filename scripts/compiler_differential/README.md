# Compiler differential

`make compiler-differential` compiles fixtures, examples, generated seeds and the failure corpus
under two compiler engines and fails on the first differing artifact. `make
compiler-differential-shipped` does the same for the shipped `native` default. Both also enforce
the two shared gates below.

## Shared gates for native ports

A port that moves work from the Python compiler to native code reuses these three mechanisms. It
does not add its own parity harness, property suite or E2E file.

### Native-to-Python fallbacks and analysis deferrals

`native_fallbacks.toml` is the one allow-list of all work native code still hands back to Python.
It covers both kinds of record:
- shipped-stage fallbacks, from `report_native_fallback(site=NativeFallbackSite.<SITE>, kind=...)`;
- preview analysis-stage deferrals: every `analysis-deferrals-*.jsonl` record (analysis session,
  lineage, semantic checks, contracts).

Every entry names an engine, stage, site and kind, with its exact count per corpus. Use
`max_counts` instead of `counts` only for a count that is not stable, and give the reason in a
comment and in the PR body.

The records cost nothing unless `SQLBUILD_ANALYSIS_RECORD_DIR` is set, which only the harness
sets. `--native-fallbacks check` runs in both make targets and fails CI in both directions:
- an entry, engine or corpus count that is not on the list fails;
- a listed entry whose count changed or that no longer occurs also fails, and the message says to
  update or remove it, so the list only shrinks.

The counts hold for the make targets' corpus (`--seeds 12`); other seed ranges are refused.

**How a PR updates the list and the goldens**

One command rewrites both from the current tree:

```sh
make compiler-baselines
```

It deletes `tests/goldens/compiler`, then runs the two CI differentials with `--native-fallbacks
update --goldens update`. Commit the resulting `native_fallbacks.toml` and `tests/goldens/` diff
in the same PR as the change that caused it.

- A port deletes the Python code it replaces in the same PR. Its entries then disappear from the
  list, and that removal is the port's test that the fallbacks are gone. When the last entry for
  a `NativeFallbackSite` goes, delete the member and its `report_native_fallback` call too.
- If the corpus does not reach a site yet, first add a failure case or seed feature that does.
- A PR that merges after a list or golden change on main reruns `make compiler-baselines` after
  rebasing and commits the result.

**What a reviewer checks in the diff**

- `native_fallbacks.toml`:
  - Removed entries and lower counts are expected from ports.
  - Every added entry, higher count or new `max_counts` needs a stated reason in the PR body.
    Never add one just to make CI pass.
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

Project paths, the SQLBuild version, invocation ids and timings are masked.

- `--goldens check` (in both make targets) compares every engine with the goldens, so an
  output-neutral port needs no new parity suite.
- `make compiler-baselines` rewrites them from the python oracle. Run it only when output
  changes on purpose, and review the diff like code.
- Seeds outside the recorded range have no golden and are skipped; any other project without a
  golden fails.
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
