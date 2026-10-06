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
| `--select`, `-s` | Select tests by name (`order_status_rules` or `test:order_status_rules`), or the tests targeting specific models |
| `--exclude` | Exclude tests by name, or the tests targeting specific models |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `query` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

Test names are globally unique, so a bare test name selects exactly that test. `test:<name>` is the
explicit form and accepts the same glob patterns as names, such as `test:orders_*`. A bare pattern
selects tests only when it matches no other resource. Test selectors are unioned with model
selectors, so `sqb test test:order_status_rules stg_orders` runs that test and every test targeting
`stg_orders`. Test selectors cannot use `+` graph expansion or `,` intersection. Only `sqb test` and
`sqb build` accept test selectors; other commands reject them with `S013`.

Parameterized cases use parent-level selection. Selecting a test or a target model includes every
case of each matching `TEST` template, and `--case` narrows the run to one case name.

Text output identifies each case as `<parent> [<case>]` and includes its source path and safe typed
parameters. Structured JSON emits one check per case with stable source/block/case identity,
declared parameter types and nullability, typed values, and a content fingerprint. Exact decimals
are strings in JSON so their scale is preserved. Each test check in JSON output reports its
`duration_ms`.

## Examples

```bash
# Run all tests
sqb test

# Run tests for a specific model
sqb test stg_orders

# Run one test by name
sqb test order_status_rules

# Run one case of a parameterized test
sqb test test:order_status_rules --case open_case
```
