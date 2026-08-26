"""Public adapter resolution from built-in and project-local registrations."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.discovery.main.builtins import builtin_adapter_classes
from sqlbuild.adapter.discovery.main.project_adapters import discover_project_adapters


def resolve_adapter(*, adapter_name: str, project_dir: Path | None = None) -> BaseAdapter:
    """Resolve one adapter without depending on CLI error types."""

    builtins: dict[str, type[BaseAdapter]] = builtin_adapter_classes()
    adapter_class: type[StrictAdapter] | None = None
    if project_dir is not None:
        adapter_class = discover_project_adapters(
            project_dir=project_dir,
            reserved_names=frozenset(builtins),
        ).get(adapter_name)
    if adapter_class is None:
        adapter_class = builtins.get(adapter_name)
    if adapter_class is None:
        available: str = ", ".join(sorted(builtins))
        local_text: str = (
            " Project-local adapters are discovered from adapters/**/*.py."
            if project_dir is not None
            else ""
        )
        raise AdapterUserError(
            f"unknown adapter '{adapter_name}'. Available built-in adapters: "
            f"{available}.{local_text}",
            code="A601",
        )
    return cast(BaseAdapter, adapter_class())
