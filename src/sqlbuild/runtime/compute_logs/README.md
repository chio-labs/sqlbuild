# Compute log storage contract

This package owns backend-neutral raw invocation stream storage and the host-local filesystem
implementation. It stores exact stdout/stderr bytes and structured `DiagnosticLog` JSONL separately
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

Selected public API examples and the operator walkthrough are documented in
[`docs/execution-observability.md`](../../../../docs/execution-observability.md).
