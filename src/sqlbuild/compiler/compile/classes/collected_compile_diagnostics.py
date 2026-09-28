"""Compile diagnostics collected during one compile phase instead of raised."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompilerDiagnostic


class CollectedCompileDiagnostics:
    """Deduplicated compile diagnostics gathered during one compile phase."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, ...], CompilerDiagnostic] = {}

    def add(self, *, key: tuple[str, ...], diagnostic: CompilerDiagnostic) -> None:
        """Record one diagnostic; a repeated key keeps the first diagnostic."""

        self._by_key.setdefault(key, diagnostic)

    @property
    def diagnostics(self) -> tuple[CompilerDiagnostic, ...]:
        """Return the recorded diagnostics in deterministic key order."""

        return tuple(self._by_key[key] for key in sorted(self._by_key))
