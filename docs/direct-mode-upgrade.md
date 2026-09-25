# Direct-mode upgrade

SQLBuild projects now run only in direct mode. Virtual environments have been removed.

Remove the following project and local configuration keys: `settings.virtual_environments`
(including `false`), `settings.changes_only`, `targets.<name>.changes_only`,
`targets.<name>.state`, and `janitor.max_checkpoints`. These keys produce explicit removal errors.
Custom materializations defining `prepare_version` also fail to load.

The `promote`, `rollback`, `reconcile`, and `state` commands, the virtual playground template,
and the `--virtual-env`, `--include-stale-upstreams`, `--changes-only`, and
`--allow-partial-diff` flags are no longer recognized. Direct freshness `--state`, clone, diff,
and janitor remain available. Use a separate target schema for branch trials.

## Concurrent microbatch state

Concurrent microbatch event IDs changed. Drop existing `_sqlbuild_microbatches` tables written
by earlier versions before the next concurrent run. SQLBuild creates the current table schema
when concurrent execution next needs it. Sequential runs never read or write this table.

Older physical tables' extra nullable columns do not prevent explicit-column reads and writes,
but old event IDs must not be mixed with the new identity scheme.
