<!-- generated-by: sqlbuild skills -->

# janitor

> Clean up stale warehouse relations.

Online: https://docs.sqlbuild.com/cli/janitor

# sqb janitor

Identifies and removes stale warehouse relations that are no longer part of the project. Requires `janitor.enabled = true` in `sqlbuild_project.toml`.

## Usage

```bash
sqb --project-dir <path> janitor [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--auto-approve` | Skip the confirmation prompt and delete immediately |
| `--retention-days` | Override the configured retention period (days) |

## Configuration

Configure janitor behavior in `sqlbuild_project.toml`:

```toml
[janitor]
enabled = true
retention_days = 30
delete_tracked_only = true
exclude_patterns = ["audit_*", "tmp_*"]
```

See [Project Configuration](../concepts/project-configuration.md) for details on janitor settings.

## Examples

```bash
# Interactive mode (prompts for confirmation)
sqb janitor

# Auto-approve deletion
sqb janitor --auto-approve

# Override retention to 7 days
sqb janitor --retention-days 7
```

## State history pruning

In addition to cleaning up stale relations, the janitor prunes old rows from `_sqlbuild_fingerprints` and `_sqlbuild_source_freshness` tables, retaining only the latest record per identity. This keeps state tables compact without affecting change detection.

## Safety

Janitor prompts for confirmation before deleting. The confirmation requires typing an exact string to prevent accidental deletion. Use `--auto-approve` only in CI or when you're certain.
