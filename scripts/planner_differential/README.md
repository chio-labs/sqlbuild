# Planner differential

The compiler differential plans every project against an empty warehouse. The planner
differential checks the plans that depend on warehouse state: it builds each project, changes
it step by step, and records what the planner decides after every step. Use it around a change
that can alter planning (for example a port of planner code): record a baseline on the tree
before the change, then check the changed tree against it.

```bash
# On the tree before the change (about 10 minutes with the defaults)
make planner-differential PLANNER_DIFFERENTIAL_MODE=record
# On the changed tree
make planner-differential
```

or call the script directly:

```bash
uv run python -m scripts.run_planner_differential record --jobs 2
uv run python -m scripts.run_planner_differential check --jobs 2
uv run python -m scripts.run_planner_differential check --projects fixture/waffle_shop seed/0
```

`check` exits 1 when any step output differs from the baseline or a project fails to run, and
prints a unified diff for every differing artifact. It writes the run it checked beside the
baseline (`<baseline>.actual/`) for closer comparison.

## Corpus

The DuckDB fixture and example projects, then the first `--seeds` (default 6) generated seed
projects that are expected to compile and use the built-in DuckDB adapter. Generated seeds are
not required to build cleanly: model failures are part of the recorded outputs. `--projects`
keeps projects whose name contains any given text and `--limit` keeps the first N.

## Mutation script

`STEPS` in `constants.py` is the script every project runs, in order. Each `PlannerStep` names an
optional mutation, the kind of model it needs (`role`, with `index` choosing among the
candidates in name order), and extra flags for `sqb plan` and `sqb build`. Flags may contain
`{model}`, `{start_cursor}` and `{end_cursor}`, filled from the target model and its built
relation. A step whose role has no model, or whose placeholders have no value, is recorded as
skipped. Targets come from the previous unselected `sqb plan --json`, so later steps follow
earlier renames.

The script covers a no-op rebuild, a query edit, a tag change (metadata only), a config change
(`on_schema_change`), a new declared column, a column rename and a model rename through
`sqb rename` (`migrate_from`), an added model, a relation dropped outside SQLBuild, source rows
added with a later cursor value, the `--max-microbatches`, cursor override, `--exclude` and
`--select` flags, a table-to-view materialization change, and `--full-refresh`. To
add a step, append a `PlannerStep`; a new kind of change adds a mutation function in
`_helpers/steps/mutations.py`. When a mutation makes planning fail, the step is recorded and the
project files are restored so later steps still run. `--steps` runs a subset (include `initial`
so later steps have targets).

## What each step records

- `sqb plan --json`: exit code, the document, and error lines;
- `sqb plan`: exit code and text;
- the planner's full `PlanOutput`, written as a canonical JSON capture when
  `SQLBUILD_PLANNER_CAPTURE_DIR` names a directory (the same encoder as the compiler stage
  captures);
- `sqb build`: exit code, summary line and error lines;
- the rows each `_sqlbuild*` state table gained and lost during the step.

Run ids, invocation ids, event ids, timings, timestamps from the run date on (such as retention
expiry), and the run directories are masked. Mappings keyed by non-string values are sorted by
key. Baselines hold only masked values, so a baseline recorded earlier on the same day or on
another day compares cleanly unless planning changed. Plans that depend on the current time
beyond these masks would show up as differences; mask them in `_helpers/capturing/canonical.py`.

Baselines are about 45 MB for the default corpus and live under
`/tmp/sqlbuild-planner-differential/` by default; they are not committed.
