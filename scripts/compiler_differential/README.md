# Compiler differential

`make compiler-differential` runs `sqb compile` and `sqb plan` once on every fixture, example,
generated seed and failure-corpus project. It fails when a project misses its corpus expectation
(success, or failure with a given first error code) or when an output differs from its golden.
With `--stage-captures` and the `--require-*-coverage` flags it also fails when the seed corpus
does not exercise every discovery, render or analysis input kind.

For ad hoc runs (one project, other seeds), call the script directly, for example
`uv run python -m scripts.run_compiler_differential --corpus --project <dir>`. The make targets
fix the corpus the goldens are recorded for.

## Golden outputs

`tests/goldens/compiler/<corpus>/<project>.json` holds one project's compile outputs:
- each command's exit code and diagnostics;
- the compiled SQL, one array item per line;
- the manifest without its volatile metadata and the SQL it repeats.

The project directory is masked as `<project>` and the harness work directory as `<work>`,
whether or not the path is resolved. The SQLBuild version, invocation ids and timings are also
masked.

Goldens hold outputs only, not stage captures: a seed's captures are about 690 KB, too large to
review. Cache facts are covered by the incremental-versus-no-cache tests instead.

- `--goldens check` (in the make target) compares every output with its golden.
- `make compiler-baselines` rewrites them from the current tree. Run it only when output changes
  on purpose, review the diff like code, and name every changed golden in the PR body. An
  output-neutral change changes no golden; new goldens belong to new corpus cases.
- `tests/goldens/compiler/seed_range.toml` records the seed range the goldens were written for.
  Every seed in that range, and every fixture, example and failure case, must have a golden.
  Seeds outside the range (ad hoc runs with more seeds) are skipped. A missing `seed_range.toml`
  fails the check for every seed project rather than skipping them.
- Dialect variants (`<seed>-postgres`, `<seed>-snowflake`) are generated for the first seed of a
  run only, so a golden is required only for the variants of the recorded `seed_start`. An ad hoc
  `--seed-start N` run checks its base seeds in the range and skips its variants.
- A PR that merges after a golden change on main reruns `make compiler-baselines` after rebasing
  and commits the result.

## User-facing errors

`engine_error_cases()` in `_helpers/corpus/failure_cases.py` lists user-facing errors with their
exact text. Each case is part of the failure corpus, so it runs in the differential and has a
golden. `tests/e2e/scripts/compiler_differential/test_engine_error_cases.py` also checks that each
reports its `expected_code`, `expected_message` and `expected_help`.

A change that adds or changes a user-facing error adds one `failure_case(...)` to it:

```python
failure_case(
    name="engine-error-<what-goes-wrong>",
    expected_code="P001",
    files=mart_body_files("SELECT ...\n"),
    expected_message="<the exact message, with <project> for the project path>",
)
```

Then it runs `make compiler-baselines` to record the new case's golden.
