<!-- generated-by: sqlbuild skills -->

# sqb seed

> Load seed CSV files into the warehouse.

Online: https://sqlbuild.com/docs/cli/seed/

Loads seed CSV files into the warehouse as tables. Seeds are fully replaced on every run.

## Usage

```bash
sqb --project-dir <path> seed [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select specific seeds by name |
| `--exclude` | Exclude specific seeds |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `build` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

## Examples

```bash
# Load all seeds
sqb seed

# Load a specific seed
sqb seed --select seed:waffle_types
```
