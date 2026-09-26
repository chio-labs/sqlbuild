<!-- generated-by: sqlbuild skills -->

# sqb check

> Run Python checks against tasks, assets, and loaders.

Online: https://sqlbuild.com/docs/cli/check/

Runs Python [checks](../concepts/python-nodes/checks.md) in isolation. Checks validate the output of tasks, assets, and loaders. For SQL relation validation, use [`sqb audit`](audit.md) instead.

## Usage

```bash
sqb --project-dir <path> check [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select checks to run (by name, `check:`, `tag:`, or graph expansion) |
| `--exclude` | Exclude checks from the selection |
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `--json` | Print check results as JSON |
| `--json-output` | Write check results JSON to a file path |
| `--vars` | Override project variables |

Selecting a non-check node is rejected; use [`sqb build`](build.md) to run tasks and assets.

## Examples

```bash
# Run all checks
sqb check

# Run one check and its required dependencies
sqb check --select +check_orders_exported

# Run checks by tag
sqb check --select tag:exports

# Print results as JSON
sqb check --json
```

## Output

Checks report PASS, FAIL, or WARN per check. A failing `error`-severity check exits non-zero; `warn`-severity failures are reported without failing the command.

Results are written to `target/run/checks/python_checks.json`.

## Relationship to build

`sqb build` runs relevant Python checks by default after the tasks, assets, and loaders they depend on have run. `sqb build --no-audits` skips checks alongside audits. `sqb check` runs only checks, on demand.
