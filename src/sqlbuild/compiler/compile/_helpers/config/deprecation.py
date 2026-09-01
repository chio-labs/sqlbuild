"""Build compile diagnostics for deprecated model configuration."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import CURSOR_INPUTS_CONFIG_KEY
from sqlbuild.compiler.compile.models import CompileModelInput, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)


def build_cursor_alias_diagnostics(
    *, model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompilerDiagnostic, ...]:
    """Build one project-level deprecation warning for the legacy cursor alias."""

    if not any(CURSOR_INPUTS_CONFIG_KEY in item.config.values for item in model_inputs):
        return ()
    return (
        CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILE,
            severity=DiagnosticSeverity.WARNING,
            code="C188",
            message=(
                "cursor_inputs is deprecated; use cursor_filter_inputs. It remains an alias "
                "until the next major release."
            ),
            resource_type=CompiledResourceType.MODEL,
        ),
    )
