"""Lazy built-in adapter registry implementation."""

from functools import cache
from importlib import import_module
from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.discovery.constants import BUILTIN_ADAPTER_IMPORTS


def adapter_names() -> frozenset[str]:
    """Return every reserved built-in adapter name."""

    return frozenset(BUILTIN_ADAPTER_IMPORTS)


@cache
def adapter_class(adapter_name: str) -> type[BaseAdapter] | None:
    """Load one built-in adapter class on demand."""

    import_spec: tuple[str, str] | None = BUILTIN_ADAPTER_IMPORTS.get(adapter_name)
    if import_spec is None:
        return None
    module_name, class_name = import_spec
    return cast(type[BaseAdapter], getattr(import_module(module_name), class_name))


def adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    classes: dict[str, type[BaseAdapter]] = {}
    for adapter_name in BUILTIN_ADAPTER_IMPORTS:
        resolved_class: type[BaseAdapter] | None = adapter_class(adapter_name)
        if resolved_class is not None:
            classes[adapter_name] = resolved_class
    return classes
