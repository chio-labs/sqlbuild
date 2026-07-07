"""Mutable dlt progress counter."""

from __future__ import annotations


class DltProgressCounter:
    def __init__(
        self,
        *,
        step: str,
        name: str,
        label: str | None,
        count: int = 0,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        self.step = step
        self.name = name
        self.label = label
        self.count = count
        self.total = total
        self.message = message
