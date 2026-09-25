from __future__ import annotations


class FakeSqlServerConnection:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)


class RowsCursor:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)


class ScriptedSqlServerConnection:
    """Record statements and answer every query with the same scripted rows."""

    def __init__(self, rows: tuple[tuple[object, ...], ...] = ()) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> RowsCursor:
        self.executed_sql.append(sql)
        return RowsCursor(self.rows)
