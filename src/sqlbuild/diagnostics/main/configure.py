"""Diagnostics logging configuration entrypoint."""

from __future__ import annotations

from sqlbuild.diagnostics.classes.invocation_diagnostic_routing import InvocationDiagnosticRouting
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions


def configure_diagnostics(
    *,
    debug: bool,
    use_color: bool = False,
    invocation_id: str = "programmatic",
) -> InvocationDiagnosticRouting:
    """Create an explicit scoped diagnostic routing context."""

    return InvocationDiagnosticRouting(
        invocation_id=invocation_id,
        options=DiagnosticRoutingOptions(
            debug_console=debug,
            use_color=use_color,
        ),
    )
