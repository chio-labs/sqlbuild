"""Collect compile diagnostics so one compile reports every violation, not only the first."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import replace
from functools import wraps

from sqlbuild.compiler.compile.classes.collected_compile_diagnostics import (
    CollectedCompileDiagnostics,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
    CompilerDiagnostic,
)

_ACTIVE_COLLECTOR: ContextVar[CollectedCompileDiagnostics | None] = ContextVar(
    "sqlbuild_collected_compile_diagnostics", default=None
)


@contextmanager
def collect_compile_diagnostics() -> Iterator[CollectedCompileDiagnostics]:
    """Collect diagnostics reported inside the block instead of raising the first one."""

    collector: CollectedCompileDiagnostics = CollectedCompileDiagnostics()
    token: Token[CollectedCompileDiagnostics | None] = _ACTIVE_COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _ACTIVE_COLLECTOR.reset(token)


def with_collected_compile_diagnostics[**P, R: (CompileProjectInputs, CompiledProject)](
    build: Callable[P, R],
) -> Callable[P, R]:
    """Append every diagnostic reported while ``build`` runs to the diagnostics it returns."""

    @wraps(build)
    def collecting(*args: P.args, **kwargs: P.kwargs) -> R:
        with collect_compile_diagnostics() as violations:
            built: R = build(*args, **kwargs)
        if not violations.diagnostics:
            return built
        return replace(built, diagnostics=(*built.diagnostics, *violations.diagnostics))

    return collecting


def report_compile_diagnostic(*, key: tuple[str, ...], diagnostic: CompilerDiagnostic) -> None:
    """Record a diagnostic in the active collector, or raise it when none is active."""

    collector: CollectedCompileDiagnostics | None = _ACTIVE_COLLECTOR.get()
    if collector is not None:
        collector.add(key=key, diagnostic=diagnostic)
        return
    location: str = (
        f"\n  --> {diagnostic.location.path.as_posix()}:{diagnostic.location.line}"
        if diagnostic.location is not None
        else f"\n  --> {diagnostic.path.as_posix()}"
        if diagnostic.path is not None
        else ""
    )
    raise CompileInputError(
        f"{diagnostic.message}{location}", code=diagnostic.code, help=diagnostic.help
    )
