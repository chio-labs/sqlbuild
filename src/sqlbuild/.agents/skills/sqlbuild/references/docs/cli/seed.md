<!-- generated-by: sqlbuild skills -->

# seed

> Load seed CSV files into the warehouse.

Online: https://docs.sqlbuild.com/cli/seed

# sqb seed

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

## Examples

```bash
# Load all seeds
sqb seed

# Load a specific seed
sqb seed --select seed:waffle_types
```
