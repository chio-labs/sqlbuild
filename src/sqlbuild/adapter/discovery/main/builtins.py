"""Compatibility entrypoint for built-in adapter class discovery."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.discovery.main.builtin_adapter_classes import (
    builtin_adapter_classes as _builtin_adapter_classes,
)


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    return _builtin_adapter_classes()
