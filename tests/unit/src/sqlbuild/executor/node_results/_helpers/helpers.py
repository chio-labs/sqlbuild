"""Helpers for node result SQL tests."""

from __future__ import annotations


def render_test_qualified_name(*, database: str | None, schema: str, name: str) -> str:
    return f"{database or ''}.{schema}.{name}".lstrip(".")
