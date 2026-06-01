from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


class RelationTargetTestAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> object:
        del connection
        return sql
