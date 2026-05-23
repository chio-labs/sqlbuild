"""Helpers for strict adapter contract tests."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.helpers.builtins import builtin_adapter_classes
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


def first_class_adapter_contract_violations() -> tuple[str, ...]:
    contract_methods: frozenset[str] = cast(Any, StrictAdapter).__abstractmethods__
    violations: list[str] = []
    adapter_cls: type[StrictAdapter]
    for adapter_cls in _first_class_adapter_classes():
        method_name: str
        for method_name in sorted(contract_methods):
            owner: type[object] | None = _method_owner(adapter_cls, method_name)
            if owner is None:
                violations.append(f"{adapter_cls.__name__}.{method_name}: missing")
                continue
            if owner in {BaseAdapter, StrictAdapter}:
                violations.append(
                    f"{adapter_cls.__name__}.{method_name}: inherited from {owner.__name__}"
                )
    return tuple(violations)


def _first_class_adapter_classes() -> tuple[type[StrictAdapter], ...]:
    return tuple(cast(type[StrictAdapter], cls) for cls in builtin_adapter_classes().values())


def _method_owner(adapter_cls: type[StrictAdapter], method_name: str) -> type[object] | None:
    cls: type[object]
    for cls in adapter_cls.__mro__:
        if method_name in cls.__dict__:
            return cls
    return None
