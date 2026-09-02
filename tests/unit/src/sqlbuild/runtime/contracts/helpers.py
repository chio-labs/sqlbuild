from __future__ import annotations

from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter


class RecordingConnectionAdapter(BaseAdapter):
    adapter_name: ClassVar[str] = "recording-connection-test"

    def __init__(self, *, events: list[str], connection: object) -> None:
        self.events = events
        self.connection = connection
        self.connected_config: dict[str, object] | None = None

    def connect(self, config: dict[str, object]) -> object:
        self.events.append("connect")
        self.connected_config = config
        return self.connection

    def close(self, connection: object) -> None:
        del connection

    def _execute(self, connection: Any, sql: str) -> object:
        del connection
        return sql


class FailingConnectionAdapter(BaseAdapter):
    adapter_name: ClassVar[str] = "failing-connection-test"

    def __init__(self, *, events: list[str], error: Exception) -> None:
        self.events = events
        self.error = error
        self.connected_config: dict[str, object] | None = None

    def connect(self, config: dict[str, object]) -> object:
        self.events.append("connect")
        self.connected_config = config
        raise self.error

    def close(self, connection: object) -> None:
        del connection

    def _execute(self, connection: Any, sql: str) -> object:
        del connection
        return sql
