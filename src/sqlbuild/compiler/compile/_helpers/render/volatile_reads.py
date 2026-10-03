"""Record per-invocation values that a reused attachment result cannot reproduce."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.compiler.compile.types import CompileContextKey, TemplateNamespace

_ACTIVE_READS: ContextVar[set[str] | None] = ContextVar(
    "sqlbuild_volatile_compile_reads", default=None
)


def environment_read_label(name: str) -> str:
    """Return the recorded label for one environment variable read."""

    return f"{TemplateNamespace.ENV}:{name}"


def note_environment_read(name: str) -> None:
    """Record that template or SQL interpolation read one environment variable."""

    reads: set[str] | None = _ACTIVE_READS.get()
    if reads is not None:
        reads.add(environment_read_label(name))


def note_context_read(name: str) -> None:
    """Record a CTX read whose value differs between compile invocations."""

    reads: set[str] | None = _ACTIVE_READS.get()
    if reads is not None and name == CompileContextKey.RUN_ID:
        reads.add(f"{TemplateNamespace.CTX}:{name}")


@contextmanager
def record_volatile_reads() -> Iterator[set[str]]:
    """Collect environment and run-id reads made while the block runs."""

    reads: set[str] = set()
    token: Token[set[str] | None] = _ACTIVE_READS.set(reads)
    try:
        yield reads
    finally:
        _ACTIVE_READS.reset(token)
