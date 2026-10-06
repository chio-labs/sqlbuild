<!-- generated-by: sqlbuild skills -->

# sqb test

> Run SQL unit tests and multi-model tests in isolation.

Online: https://sqlbuild.com/docs/cli/test/

Runs SQL unit tests, independently reported parameterized cases, and multi-model tests without
building models. Useful for validating test logic independently.

## Usage

```bash
sqb test [SELECTOR ...] [flags]
```

Positional `SELECTOR` arguments work like `--select`, and both forms can be combined. `--project-dir <path>`, `--no-color`, and `--debug` can go before or after the command name.

## Flags

| Flag | Description |
|------|-------------|
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `SELECTOR ...` | Positional selectors, the same as `--select` |
| `--select`, `-s` | Select tests targeting specific models |
| `--exclude` | Exclude tests targeting specific models |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `query` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

Parameterized cases use parent-level selection. Selecting a target model includes every case in
each matching `TEST` template; case names are not model selectors.

Text output identifies each case as `<parent> [<case>]` and includes its source path and safe typed
parameters. Structured JSON emits one check per case with stable source/block/case identity,
declared parameter types and nullability, typed values, and a content fingerprint. Exact decimals
are strings in JSON so their scale is preserved.

## Examples

```bash
# Run all tests
sqb test

# Run tests for a specific model
sqb test stg_orders
```
