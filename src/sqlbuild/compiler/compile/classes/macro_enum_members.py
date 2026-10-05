"""One enum's members as a Python SQL macro sees them."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import MacroDeclarationLookupError


class MacroEnumMembers(Mapping[str, str | int]):
    """One enum's members as a macro sees them."""

    def __init__(
        self,
        *,
        enum_name: str,
        values: Mapping[str, str | int],
        file_path: Path,
        on_miss: Callable[[], None],
    ) -> None:
        self._enum_name: str = enum_name
        self._values: Mapping[str, str | int] = values
        self._file_path: Path = file_path
        self._on_miss: Callable[[], None] = on_miss

    def __getitem__(self, name: str) -> str | int:
        if name in self._values:
            return self._values[name]
        self._on_miss()
        available: str = ", ".join(sorted(self._values)) or "none"
        raise MacroDeclarationLookupError(
            f"Unknown member '{name}' for enum '{self._enum_name}' in '{self._file_path}'. "
            f"Available members: {available}"
        )

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)
