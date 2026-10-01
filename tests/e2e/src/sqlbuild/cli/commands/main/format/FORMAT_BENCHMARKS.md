# Format performance benchmarks

`test_format_performance.py` bounds `sqb format --check` on generated projects with neutral
orders-style names. The guards run in the `Formatter performance guards` CI job with `-n auto`,
so budgets allow for the other guards running concurrently.

## Contract fixtures

1,000 SQL test files whose fixtures carry typed NULL projections. Both the full format and the
`--fixtures-only` path are bounded, and fixture formatting must scale linearly across 500, 1,000
and 2,000 files.

## Unformatted models

1,300 unformatted models in a fixed mix: every tenth model projects 300 computed columns, three in
ten are six-CTE chains with window functions and line comments, and the rest are short joins with
block comments and `IN` lists. Each model reads the previous one through `__ref`, so formatting
also restores intrinsic calls. A separate case formats one 6,000-line model with 3,000 chained
CTEs, which bounds per-token work on very large files.

Budgets, about 1.5 to 2 times the typical time measured with the guards running in parallel:

- 1,300 models: format phase under 1.5 seconds, end to end under 3.5 seconds;
- one 6,000-line model: format phase under 0.75 seconds, end to end under 2.5 seconds;
- 325, 650 and 1,300 models: each doubling at most 2.75 times the format-phase time.

The format phase is the `Formatting SQL` timing that the command prints, so process startup and
discovery do not mask a formatter regression.
