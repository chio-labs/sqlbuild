"""Test case types for pipeline helper tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeferredTargetTestCase:
    description: str
    adapter_name: str
    logical_schema: str | None
    logical_database: str | None
    env_schema: str | None
    env_database: str | None
    effective_vars: dict[str, str]
    default_schema: str | None
    default_database: str | None
    expected_schema: str | None
    expected_database: str | None
    expected_qualified_name: str | None
