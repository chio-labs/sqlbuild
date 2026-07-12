"""Adapter resolution from project configuration."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.helpers.builtins import builtin_adapter_classes
from sqlbuild.adapter.shared.main.project_adapters import discover_project_adapters
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.cli.commands.shared.exceptions import CliUserError


def resolve_adapter(*, adapter_name: str, project_dir: Path | None = None) -> BaseAdapter:
    """Resolve an adapter name from project config to an adapter instance."""

    builtin_adapters: dict[str, type[BaseAdapter]] = builtin_adapter_classes()
    adapter_class: type[StrictAdapter] | None = None
    if project_dir is not None:
        local_adapters: dict[str, type[StrictAdapter]] = discover_project_adapters(
            project_dir=project_dir,
            reserved_names=frozenset(builtin_adapters),
        )
        adapter_class = local_adapters.get(adapter_name)
    if adapter_class is None:
        adapter_class = builtin_adapters.get(adapter_name)
    if adapter_class is None:
        available: tuple[str, ...] = tuple(sorted(builtin_adapters))
        local_text: str = ""
        if project_dir is not None:
            local_text = " Project-local adapters are discovered from adapters/**/*.py."
        raise CliUserError(
            f"unknown adapter '{adapter_name}'. Available built-in adapters: "
            f"{', '.join(available)}.{local_text}",
            code="C601",
        )
    return cast(BaseAdapter, adapter_class())
