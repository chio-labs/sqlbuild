<!-- generated-by: sqlbuild skills -->

# state

> Manage the virtual mode state store.

Online: https://docs.sqlbuild.com/cli/state

## Contents

- Usage
- Subcommands

# sqb state

Manages the virtual mode state store lifecycle, locks, and checkpoints. Requires `virtual_environments = true`.

## Usage

```bash
sqb state <subcommand> [flags]
```

## Subcommands

### init

Create state tables in the configured schema.

```bash
sqb state init
```

### migrate

Back up the current state schema and re-initialize state tables. Creates a backup schema (e.g. `sqlbuild_state__backup_<id>`) before re-initializing.

```bash
sqb state migrate
```

### rollback

Restore state from a backup.

```bash
# Restore from the latest backup
sqb state rollback

# Restore from a specific backup
sqb state rollback --backup-id <id>
```

### reset

Drop all state tables. Requires `allow_reset = true` in the target state config and `--auto-approve` on the command line.

```bash
sqb state reset --auto-approve
```

### adopt

Convert existing stateless warehouse relations into versioned physical relations with VDE views. Interactive only - requires typed confirmation.

```bash
sqb state adopt [--allow-copy]
```

| Flag | Description |
|------|-------------|
| `--allow-copy` | Allow CTAS copy fallback when native rename is not available |

See [Adopt and Detach](../concepts/virtual-environments/adopt-detach.md) for details.

### detach

Collapse a VDE back into stateless warehouse relations. Interactive only - requires typed confirmation. The VDE must be finalized.

```bash
sqb state detach [--allow-copy]
```

| Flag | Description |
|------|-------------|
| `--allow-copy` | Allow CTAS copy fallback when native rename is not available |

### locks

List active locks in the state store.

```bash
sqb state locks
```

### locks clear

Clear a stuck lock.

```bash
sqb state locks clear <lock_key> --force
```

Only clear locks when you are certain the holding operation is no longer running.

### checkpoints list

List finalized checkpoints for a VDE.

```bash
sqb state checkpoints list [--virtual-env <name>]
```

### checkpoints show

Show the model refs stored in a checkpoint.

```bash
sqb state checkpoints show <checkpoint_id> [--virtual-env <name>]
```

### checkpoints diff

Diff current VDE refs against a checkpoint.

```bash
sqb state checkpoints diff <checkpoint_id> [--virtual-env <name>]
```
