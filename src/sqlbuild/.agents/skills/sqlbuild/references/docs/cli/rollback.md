<!-- generated-by: sqlbuild skills -->

# rollback

> Roll back a VDE to a prior finalized checkpoint.

Online: https://docs.sqlbuild.com/cli/rollback

# sqb rollback

Restores a virtual environment to a prior finalized checkpoint by rebinding its refs and refreshing logical views. Virtual mode only.

## Usage

```bash
sqb rollback [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--virtual-env` | Target VDE name (defaults to active target name) |
| `--checkpoint-id` | Restore a specific checkpoint instead of the previous one |
| `--select`, `-s` | Roll back specific models only |
| `--exclude` | Exclude specific models |
| `--allow-partial-rollback` | Accept a working VDE when partial rollback leaves downstream stale |
| `--include-stale-upstreams` | Add required upstream refs from the checkpoint |
| `--verbose`, `-v` | Show uncapped model sets |
| `--var` | Set project variables |

## Examples

```bash
# Roll back to the previous finalized checkpoint
sqb rollback

# Roll back a specific VDE
sqb rollback --virtual-env pr_123

# Roll back to a specific checkpoint
sqb rollback --checkpoint-id <id>

# Partial rollback
sqb rollback --select fact_orders --allow-partial-rollback
```

See [Rollback](../concepts/virtual-environments/rollback.md) for details on checkpoints, rollback behavior, and guards.
