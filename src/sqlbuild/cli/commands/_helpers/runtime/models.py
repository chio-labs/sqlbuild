"""CLI command runtime models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.classes.base_adapter import BaseAdapter


@dataclass(frozen=True)
class AdapterConnectionContext:
    """Resolved adapter and connection configuration for one CLI command."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
