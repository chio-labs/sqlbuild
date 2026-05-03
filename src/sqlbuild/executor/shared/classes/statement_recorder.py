"""Runtime SQL statement recording."""

from __future__ import annotations

from collections.abc import Iterable


class StatementRecorder:
    def __init__(self) -> None:
        self._statements: list[str] = []

    def record(self, statement: str) -> None:
        self._statements.append(statement)

    def record_many(self, statements: Iterable[str]) -> None:
        self._statements.extend(statements)

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._statements)
