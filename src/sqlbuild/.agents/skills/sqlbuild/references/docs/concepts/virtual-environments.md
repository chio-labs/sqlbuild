<!-- generated-by: sqlbuild skills -->

# Overview

> Version-controlled SQL pipeline environments with instant promotion and rollback.

Online: https://docs.sqlbuild.com/concepts/virtual-environments

## Contents

- When to use virtual environments
- How it works
- Try it
- Example workflow
- What's next

Virtual environments are in alpha. The core workflow (build, promote, rollback, reconcile) is functional and tested across supported adapters. The API and CLI surface may evolve based on feedback. Do not use virtual environments for production workloads yet.

Virtual environments (VDEs) let you build, preview, and promote SQL pipeline changes without recomputing models. Each VDE is a set of pointers to versioned physical relations. Creating a new VDE is instant (pointer copy, no data duplication), and promoting one VDE into another is a view swap, not a rebuild.

## When to use virtual environments

- **PR preview environments** - build a VDE per pull request against a production warehouse, validate with audits and tests, then promote the built versions to production without rebuilding
- **Blue/green deployments** - build into a staging VDE, promote to production atomically
- **Multi-developer isolation** - each developer works in their own VDE without conflicting with others, sharing physical versions when code is identical
- **Instant rollback** - revert production to a prior finalized state by restoring a checkpoint's pointer set

Virtual environments are opt-in via `virtual_environments = true` (under `[settings]`) and require a state store. Projects that don't need environment isolation or promotion workflows should use the default direct mode.

## How it works

### Targets and virtual environments

In virtual mode there are two separate concepts:

**Targets** are the existing SQLBuild build contexts from `sqlbuild_project.toml` (e.g. `dev`, `prod`). They choose the warehouse connection, schema, and state database. In virtual mode they are sometimes called *physical targets* to distinguish them from VDEs.

**Virtual data environments (VDEs)** are versioned pointer sets stored in the state database. They choose which model versions the logical views point to.

```bash
sqb --target prod build --virtual-env pr_123
```

This means: use the `prod` physical target (warehouse, state DB), but build into the `pr_123` virtual environment.

### Version identity

Model versions are identified by content hashes, not sequence numbers. The hash includes the model's query SQL, version-identity config, and upstream version hashes. If two developers compile identical code with identical upstream versions, they get the same hash and reuse the same physical relation. No data is duplicated.

### Physical and logical relations

Virtual mode creates two types of warehouse objects:

- **Physical version relations** store actual data: `<schema>__sqb_physical.<model>__v_<hash>`
- **Logical VDE views** point to physical versions: `<schema>__<vde_name>.<model>` as `SELECT * FROM <physical_version>`

Users query the logical views. SQLBuild manages the physical layer.

### Zero-copy branching

Creating a new VDE from a baseline copies only pointer rows in the state database, not data. Unchanged models share the same physical relations across VDEs.

### Instant promotion

Promoting VDE `pr_123` to `prod` updates the pointer rows and refreshes the logical views. No models are rebuilt. If every model in the source VDE has already been built and validated, promotion is a metadata operation.

## Try it

```bash
sqb playground --template virtual
cd sqlbuild-playground
sqb state init
sqb build
sqb build --virtual-env pr
sqb diff dev:pr --schema-only --allow-partial-diff
sqb promote --from pr --to dev
sqb state checkpoints list
sqb rollback
```

This creates a self-contained DuckDB project with loaders, models, tests, scenarios, and a local state store. No warehouse credentials required.

## Example workflow

```bash
# Initialize state store
sqb state init

# First build creates physical versions and default VDE
sqb build

# Create a PR preview VDE
sqb build --virtual-env pr_123

# Modify a model, rebuild in the PR VDE
sqb build --virtual-env pr_123

# Compare VDEs
sqb diff dev:pr_123

# Promote PR versions to the default VDE
sqb promote --from pr_123 --to dev
```

## What's next

- [Setup](virtual-environments/setup.md) - configuration and state initialization
- [Building](virtual-environments/building.md) - virtual builds, partial builds, seeded incrementals
- [Promotion](virtual-environments/promotion.md) - promoting VDEs
- [Rollback](virtual-environments/rollback.md) - checkpoints and rollback
- [Clone](virtual-environments/clone.md) - hydrating physical versions from a source warehouse
- [Diff](virtual-environments/diff.md) - comparing VDE ref sets
- [Adopt and Detach](virtual-environments/adopt-detach.md) - migrating existing projects
- [Reconcile](virtual-environments/reconcile.md) - diagnosing and repairing drift
- [Locks](virtual-environments/locks.md) - concurrent access control
- [Janitor](virtual-environments/janitor.md) - cleanup and retention
- [Recovery](virtual-environments/recovery.md) - what to do when things break
