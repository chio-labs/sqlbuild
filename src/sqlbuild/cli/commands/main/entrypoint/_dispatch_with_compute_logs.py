"""Best-effort local compute capture around the existing history dispatch."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.compute_log_diagnostics import (
    log_compute_capture_failure,
)
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.main.entrypoint._dispatch_with_history import _creates_project
from sqlbuild.compute_logs import (
    COMPUTE_LOG_FORMAT_VERSION,
    CaptureMetadata,
)
from sqlbuild.diagnostics.classes.invocation_diagnostic_routing import InvocationDiagnosticRouting
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.observability import ExecutionIdentity
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.compute_logs.classes.local_filesystem_compute_log_storage import (
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.runtime.compute_logs.classes.scoped_compute_log_capture import (
    ScopedComputeLogCapture,
)


def dispatch_with_compute_logs(
    *, args: CliNamespace, identity: ExecutionIdentity, operation: Callable[[], int]
) -> int:
    """Run one composed dispatch while retaining exact process streams best-effort."""

    if _creates_project(args=args):
        return operation()
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    routing_options: DiagnosticRoutingOptions = DiagnosticRoutingOptions(
        debug_console=args.debug,
        use_color=(not args.no_color) and supports_color(),
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
        )
        with routing:
            for failure, channel in failures:
                log_compute_capture_failure(error=failure, channel=channel)
            return operation()
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda error, channel: log_compute_capture_failure(
            error=error, channel=channel
        ),
        routing_options=routing_options,
    )
    return capture.run(operation=operation)
