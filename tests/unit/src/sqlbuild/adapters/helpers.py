from __future__ import annotations


class AdapterCursorMaxCursor:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.closed: bool = False
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def close(self) -> None:
        self.closed = True


class AdapterExecuteRecordingConnection:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.cursor: AdapterCursorMaxCursor = AdapterCursorMaxCursor(rows=rows)
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> AdapterCursorMaxCursor:
        self.executed_sql.append(sql)
        return self.cursor


class AdapterCursorRecordingConnection:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.cursor_instance: AdapterCursorMaxCursor = AdapterCursorMaxCursor(rows=rows)

    def cursor(self) -> AdapterCursorMaxCursor:
        return self.cursor_instance


def adapter_cursor_executed_sql(connection: object) -> tuple[str, ...]:
    if isinstance(connection, AdapterExecuteRecordingConnection):
        return tuple(connection.executed_sql)
    if isinstance(connection, AdapterCursorRecordingConnection):
        return tuple(connection.cursor_instance.executed_sql)
    raise TypeError(f"unsupported connection type: {type(connection).__name__}")


def adapter_closed_cursor_count(connection: object) -> int:
    if isinstance(connection, AdapterExecuteRecordingConnection):
        return 0
    if isinstance(connection, AdapterCursorRecordingConnection):
        return int(connection.cursor_instance.closed)
    raise TypeError(f"unsupported connection type: {type(connection).__name__}")
