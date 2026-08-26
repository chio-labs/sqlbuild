"""Compiler tolerant discovery for offline declaration-scope inspection."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.aggregation import (
    build_tolerant_scope_discovery,
)
from sqlbuild.compiler.discovery.models import TolerantScopeDiscovery


def discover_scope_snapshot(*, project_dir: Path) -> TolerantScopeDiscovery:
    """Parse scope-relevant authored roots while retaining independent file faults."""

    return build_tolerant_scope_discovery(project_dir=project_dir)
