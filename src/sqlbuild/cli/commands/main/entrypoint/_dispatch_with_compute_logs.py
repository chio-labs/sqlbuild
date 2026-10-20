"""Best-effort local compute capture around canonical lifecycle dispatch."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlbuild._native import (
    COMPUTE_LOG_FORMAT_VERSION,
    CliNamespace,
    LocalFilesystemComputeLogStorage,
    RecallLifecycleSink,
    supports_color,
)
from sqlbuild.cli.commands._helpers.entry.compute_log_diagnostics import (
    log_compute_capture_failure,
)
from sqlbuild.diagnostics.classes.invocation_diagnostic_routing import InvocationDiagnosticRouting
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.diagnostics.main.diagnostic_project_roots import diagnostic_project_roots
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.runtime.compute_logs.main.run_with_compute_log_capture import (
    run_with_compute_log_capture,
)
from sqlbuild.runtime.compute_logs.models import CaptureMetadata
from sqlbuild.runtime.observability.models import ExecutionIdentity


def dispatch_with_compute_logs(
    *,
    args: CliNamespace,
    identity: ExecutionIdentity,
    operation: Callable[[], int],
    creates_project: bool,
    recall: RecallLifecycleSink | None = None,
) -> int:
    """Run one composed dispatch while retaining exact process streams best-effort."""

    if creates_project:
        return operation()
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    project_roots: tuple[str, ...] = diagnostic_project_roots(project_dir=project_dir)
    routing_options: DiagnosticRoutingOptions = DiagnosticRoutingOptions(
        debug_console=args.debug,
        use_color=(not args.no_color) and supports_color(),
        project_roots=project_roots,
    )
    started_at: datetime = datetime.now(UTC)
    command: str = "unknown" if args.command is None else str(args.command)
    metadata: CaptureMetadata = CaptureMetadata(
        format_version=COMPUTE_LOG_FORMAT_VERSION,
        invocation_id=identity.invocation_id,
        command=command,
        project_dir=str(project_dir.resolve()),
        started_at=started_at,
        capture_date=started_at.date().isoformat(),
        target=args.target,
        run_id=identity.run_id,
    )
    storage: LocalFilesystemComputeLogStorage | None = None
    try:
        storage = LocalFilesystemComputeLogStorage(project_dir=project_dir)
        if recall is not None:
            storage.attach_recall(recall)
        storage.start_capture(metadata)
    except Exception as error:
        failures: list[tuple[Exception, str]] = [(error, "capture_open")]
        if storage is not None:
            try:
                storage.close()
            except Exception as close_error:
                failures.append((close_error, "capture_close"))
        routing: InvocationDiagnosticRouting = configure_diagnostics(
            invocation_id=identity.invocation_id,
            debug=args.debug,
            use_color=routing_options.use_color,
            project_roots=project_roots,
        )
        with routing:
            for failure, channel in failures:
                log_compute_capture_failure(error=failure, channel=channel)
            return operation()
    return run_with_compute_log_capture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda error, channel: log_compute_capture_failure(
            error=error, channel=channel
        ),
        routing_options=routing_options,
        operation=operation,
    )
