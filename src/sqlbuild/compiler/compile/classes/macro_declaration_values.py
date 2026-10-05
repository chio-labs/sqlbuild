"""Read-only declaration mappings exposed to Python SQL macros."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import MacroDeclarationLookupError
from sqlbuild.compiler.scopes.models import DeclarationRecord


class MacroDeclarationValues(Mapping[str, object]):
    """Caller-visible constants or enums that record each name a macro reads."""

    def __init__(
        self,
        *,
        values: Mapping[str, object],
        inaccessible: Mapping[str, DeclarationRecord],
        declaration_kind: str,
        file_path: Path,
        on_access: Callable[[str], None],
        on_miss: Callable[[], None],
    ) -> None:
        self._values: Mapping[str, object] = values
        self._inaccessible: Mapping[str, DeclarationRecord] = inaccessible
        self._declaration_kind: str = declaration_kind
        self._file_path: Path = file_path
        self._on_access: Callable[[str], None] = on_access
        self._on_miss: Callable[[], None] = on_miss

    def __getitem__(self, name: str) -> object:
        if name in self._values:
            self._on_access(name)
            return self._values[name]
        self._on_miss()
        inaccessible: DeclarationRecord | None = self._inaccessible.get(name)
        if inaccessible is not None:
            owner: str = inaccessible.owning_path or "global"
            raise MacroDeclarationLookupError(
                f"{self._declaration_kind.title()} '{name}' in '{self._file_path}' is "
                f"inaccessible. Defined at '{inaccessible.path}:{inaccessible.line}:"
                f"{inaccessible.column}' with scope owner '{owner}'"
            )
        visible: str = ", ".join(sorted(self._values)) or "none"
        raise MacroDeclarationLookupError(
            f"Unknown {self._declaration_kind} '{name}' in '{self._file_path}'. "
            f"Visible {self._declaration_kind}s: {visible}"
        )

    def __iter__(self) -> Iterator[str]:
        for name in self._values:
            self._on_access(name)
            yield name

    def __len__(self) -> int:
        for name in self._values:
            self._on_access(name)
        return len(self._values)
