"""Diagnostics logging configuration entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.diagnostics.classes.invocation_diagnostic_routing import InvocationDiagnosticRouting
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions


def configure_diagnostics(
    *,
    target_dir: Path,
    debug: bool,
    use_color: bool = False,
    invocation_id: str = "programmatic",
    include_sql_text: bool = False,
    write_legacy_file: bool = True,
) -> InvocationDiagnosticRouting:
    """Create an explicit scoped diagnostic routing context."""

    return InvocationDiagnosticRouting(
        target_dir=target_dir,
        invocation_id=invocation_id,
        options=DiagnosticRoutingOptions(
            debug_console=debug,
            use_color=use_color,
            include_sql_text=include_sql_text,
            write_legacy_file=write_legacy_file,
        ),
    )
