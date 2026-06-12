"""Helpers for node result main entrypoint tests."""

from __future__ import annotations

from typing import Any


class NodeResultReadFakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows: list[tuple[Any, ...]] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def fake_relation_exists(*_args: object, **_kwargs: object) -> bool:
    return True


def fake_render_qualified_name(*, database: str | None, schema: str, name: str) -> str:
    del database
    return f"{schema}.{name}"
