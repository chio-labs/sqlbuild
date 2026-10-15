# Compute log storage contract

This package owns the backend-neutral compute log shapes and the Python stream capture around a
command. The host-local filesystem storage is native (`sqlbuild._native.LocalFilesystemComputeLogStorage`,
built on `crates/sqlbuild-cli/src/compute_logs`) and is re-exported by `sqlbuild.compute_logs`. It stores exact stdout/stderr bytes and structured `DiagnosticLog` JSONL separately
from canonical lifecycle history.

The default root is `logs/`, with captures at
`logs/<UTC-date>/<invocation_id>/{metadata.json,stdout.log,stderr.log,diagnostics.jsonl,complete}`.
The empty completion marker proves capture finalization only. Reads use exact nonnegative byte
cursors. The default prune policy retains 20 complete captures while preserving every incomplete
one. CLI-managed capture invokes pruning after successful finalization; direct storage users call
`prune()` explicitly.

The local implementation rejects symlink roots and path escapes but leaves modes to directory
ownership and the process umask. It is host-local and may contain sensitive output. It does not
provide object storage, lifecycle authority, or a cross-host log service.

Operator documentation is at
[sqlbuild.com/docs/concepts/observability](https://sqlbuild.com/docs/concepts/observability/).
