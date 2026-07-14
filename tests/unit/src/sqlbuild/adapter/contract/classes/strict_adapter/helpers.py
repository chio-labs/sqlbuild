"""Helpers for strict adapter contract tests."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.discovery.main.builtins import builtin_adapter_classes


def first_class_adapter_contract_violations() -> tuple[str, ...]:
    contract_methods: frozenset[str] = cast(Any, StrictAdapter).__abstractmethods__
    violations: list[str] = []
    adapter_cls: type[StrictAdapter]
    for adapter_cls in _first_class_adapter_classes():
        method_name: str
        for method_name in sorted(contract_methods):
            owner: type[object] | None = _method_owner(adapter_cls, method_name)
            _MISSING_METHOD_COLLECTORS[owner is None](violations, adapter_cls, method_name, owner)
            _INHERITED_METHOD_COLLECTORS[owner in {BaseAdapter, StrictAdapter}](
                violations, adapter_cls, method_name, owner
            )
    return tuple(violations)


def _first_class_adapter_classes() -> tuple[type[StrictAdapter], ...]:
    return tuple(cast(type[StrictAdapter], cls) for cls in builtin_adapter_classes().values())


def _method_owner(adapter_cls: type[StrictAdapter], method_name: str) -> type[object] | None:
    owners: dict[str, type[object]] = {}
    cls: type[object]
    for cls in adapter_cls.__mro__:
        _METHOD_OWNER_COLLECTORS[method_name in cls.__dict__](owners, cls)
    return owners.get("owner")


def _collect_missing_method(
    violations: list[str],
    adapter_cls: type[StrictAdapter],
    method_name: str,
    owner: type[object] | None,
) -> None:
    del owner
    violations.append(f"{adapter_cls.__name__}.{method_name}: missing")


def _collect_inherited_method(
    violations: list[str],
    adapter_cls: type[StrictAdapter],
    method_name: str,
    owner: type[object] | None,
) -> None:
    inherited_owner: type[object] = cast(type[object], owner)
    violations.append(
        f"{adapter_cls.__name__}.{method_name}: inherited from {inherited_owner.__name__}"
    )


def _skip_method_violation(
    violations: list[str],
    adapter_cls: type[StrictAdapter],
    method_name: str,
    owner: type[object] | None,
) -> None:
    del violations, adapter_cls, method_name, owner


def _collect_method_owner(owners: dict[str, type[object]], cls: type[object]) -> None:
    owners.setdefault("owner", cls)


def _skip_method_owner(owners: dict[str, type[object]], cls: type[object]) -> None:
    del owners, cls


_MISSING_METHOD_COLLECTORS: MappingProxyType[bool, Callable[..., None]] = MappingProxyType(
    {False: _skip_method_violation, True: _collect_missing_method}
)
_INHERITED_METHOD_COLLECTORS: MappingProxyType[bool, Callable[..., None]] = MappingProxyType(
    {False: _skip_method_violation, True: _collect_inherited_method}
)
_METHOD_OWNER_COLLECTORS: MappingProxyType[bool, Callable[..., None]] = MappingProxyType(
    {False: _skip_method_owner, True: _collect_method_owner}
)
