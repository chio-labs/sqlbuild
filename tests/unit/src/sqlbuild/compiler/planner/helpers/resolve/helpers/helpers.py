"""Test helpers for resolve helper tests."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledRelationTarget


def build_target(qualified: str | None, name: str) -> CompiledRelationTarget:
    """Build a minimal target for deferred tests."""

    return CompiledRelationTarget(database=None, schema=None, name=name, qualified_name=qualified)
