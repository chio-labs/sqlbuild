"""SQLite connection wrapper with one in-process writer per database file."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Sequence

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.sqlite._helpers.statements import leading_keyword
from sqlbuild.adapters.sqlite.classes.write_gate import WriteGate
from sqlbuild.adapters.sqlite.classes.write_gates import WriteGates
from sqlbuild.adapters.sqlite.constants import (
    DATABASE_LOCKED_CODE,
    LOCKED_ERROR_FRAGMENTS,
    MEMORY_DATABASE_PATH,
    READ_STATEMENT_KEYWORDS,
)

_WRITE_GATES: WriteGates = WriteGates()


class SqliteConnection:
    """Serialize this process's writers per file so only other processes wait on busy_timeout."""

    def __init__(
        self, *, raw_connection: sqlite3.Connection, path: str, busy_timeout_seconds: float
    ) -> None:
        self.raw_connection: sqlite3.Connection = raw_connection
        self.path: str = path
        self.busy_timeout_seconds: float = busy_timeout_seconds
        self._gate: WriteGate = _WRITE_GATES.for_file(
            path if path != MEMORY_DATABASE_PATH else f"{path}{id(raw_connection)}"
        )
        self._holds_gate: bool = False

    def execute(self, sql: str) -> ObservedCursor:
        return self.execute_with(sql=sql, parameters=())

    def execute_with(self, *, sql: str, parameters: Sequence[object]) -> ObservedCursor:
        return self._run(sql=sql, run=lambda cursor: cursor.execute(sql, parameters))

    def execute_as_writer(self, sql: str) -> ObservedCursor:
        """Run a statement that needs the writer gate, such as switching a new file to WAL."""

        return self._run(sql=sql, run=lambda cursor: cursor.execute(sql), writes=True)

    def executemany(self, *, sql: str, rows: Iterable[Sequence[object]]) -> ObservedCursor:
        return self._run(sql=sql, run=lambda cursor: cursor.executemany(sql, rows))

    def _run(
        self, *, sql: str, run: Callable[[ObservedCursor], object], writes: bool = False
    ) -> ObservedCursor:
        self._enter(sql=sql, writes=writes)
        cursor: ObservedCursor = self.cursor()
        try:
            run(cursor)
        except sqlite3.Error as error:
            coded: AdapterUserError | None = self._locked_error(error)
            if coded is None:
                raise
            raise coded from error
        finally:
            self._leave()
        return cursor

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="sqlite")

    def in_transaction(self) -> bool:
        return self.raw_connection.in_transaction

    def interrupt(self) -> None:
        self.raw_connection.interrupt()

    def close(self) -> None:
        try:
            self.raw_connection.close()
        finally:
            self._release()

    def _enter(self, *, sql: str, writes: bool) -> None:
        if self._holds_gate or (not writes and leading_keyword(sql) in READ_STATEMENT_KEYWORDS):
            return
        self._holds_gate = self._gate.acquire()

    def _leave(self) -> None:
        if self._holds_gate and not self.raw_connection.in_transaction:
            self._release()

    def _release(self) -> None:
        if self._holds_gate:
            self._holds_gate = False
            self._gate.release()

    def _locked_error(self, error: sqlite3.Error) -> AdapterUserError | None:
        message: str = str(error)
        if any(fragment in message.lower() for fragment in LOCKED_ERROR_FRAGMENTS):
            return AdapterUserError(
                message=(
                    f"SQLite database '{self.path}' is locked by another writer "
                    f"(waited {self.busy_timeout_seconds:g}s)"
                ),
                code=DATABASE_LOCKED_CODE,
                help=(
                    "Another process is writing to this file. Retry when it finishes, or raise "
                    "busy_timeout in the connection settings."
                ),
            )
        return None
