"""Test case types for pipeline helper tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.python_nodes.types import PythonIdentityStatus


@dataclass(frozen=True)
class DeferredTargetTestCase:
    description: str
    render_qualified_name: Callable[..., str | None]
    logical_schema: str | None
    logical_database: str | None
    env_schema: str | None
    env_database: str | None
    effective_vars: dict[str, object]
    default_schema: str | None
    default_database: str | None
    expected_schema: str | None
    expected_database: str | None
    expected_qualified_name: str | None


@dataclass(frozen=True)
class PythonPlanIdentityStatusTestCase:
    description: str
    previous_version_hash: str | None
    expected_status: PythonIdentityStatus
