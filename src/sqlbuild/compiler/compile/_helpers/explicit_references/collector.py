"""Collect explicit-reference violations so one compile reports all of them."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import replace
from functools import wraps

from sqlbuild.compiler.compile.classes.explicit_reference_violations import (
    ExplicitReferenceViolations,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileProjectInputs, CompilerDiagnostic

_ACTIVE_COLLECTOR: ContextVar[ExplicitReferenceViolations | None] = ContextVar(
    "sqlbuild_explicit_reference_violations", default=None
)


@contextmanager
def collect_explicit_reference_violations() -> Iterator[ExplicitReferenceViolations]:
    """Collect violations reported inside the block instead of raising the first one."""

    collector: ExplicitReferenceViolations = ExplicitReferenceViolations()
    token: Token[ExplicitReferenceViolations | None] = _ACTIVE_COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _ACTIVE_COLLECTOR.reset(token)


def with_explicit_reference_diagnostics[**P](
    build: Callable[P, CompileProjectInputs],
) -> Callable[P, CompileProjectInputs]:
    """Append every violation reported while building compile inputs to their diagnostics."""

    @wraps(build)
    def collecting(*args: P.args, **kwargs: P.kwargs) -> CompileProjectInputs:
        with collect_explicit_reference_violations() as violations:
            inputs: CompileProjectInputs = build(*args, **kwargs)
        if not violations.diagnostics:
            return inputs
        return replace(inputs, diagnostics=(*inputs.diagnostics, *violations.diagnostics))

    return collecting


def report_explicit_reference_violation(
    *, key: tuple[str, ...], diagnostic: CompilerDiagnostic
) -> None:
    """Record a violation in the active collector, or raise it when none is active."""

    collector: ExplicitReferenceViolations | None = _ACTIVE_COLLECTOR.get()
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
