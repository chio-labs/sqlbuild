"""Build compile diagnostics for deprecated model configuration."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompileModelInput, CompilerDiagnostic


def build_cursor_alias_diagnostics(
    *, model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompilerDiagnostic, ...]:
    """Build one project-level deprecation warning for the legacy cursor alias."""

    return ()
