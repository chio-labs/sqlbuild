"""Explicit-reference violations gathered during one compile phase."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompilerDiagnostic


class ExplicitReferenceViolations:
    """Deduplicated explicit-reference diagnostics gathered during one compile phase."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, ...], CompilerDiagnostic] = {}

    def add(self, *, key: tuple[str, ...], diagnostic: CompilerDiagnostic) -> None:
        """Record one violation; a repeated key keeps the first diagnostic."""

        self._by_key.setdefault(key, diagnostic)

    @property
    def diagnostics(self) -> tuple[CompilerDiagnostic, ...]:
        """Return the recorded diagnostics in deterministic key order."""

        return tuple(self._by_key[key] for key in sorted(self._by_key))
