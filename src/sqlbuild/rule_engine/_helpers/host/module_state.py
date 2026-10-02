"""Detect custom-rule module state that one evaluation could leave for another."""

from __future__ import annotations

import enum
import hashlib
import os
import re
from collections import deque
from collections.abc import Iterable
from decimal import Decimal
from fractions import Fraction
from pathlib import Path, PurePath
from types import BuiltinFunctionType, FunctionType, MethodType, ModuleType
from typing import Any, cast

from sqlbuild.rule_engine.exceptions import OpaqueModuleStateError

_MAX_STATE_NODES: int = 50_000
_ATOMIC_TYPES: tuple[type, ...] = (
    type(None),
    bool,
    int,
    float,
    complex,
    str,
    bytes,
    bytearray,
    Decimal,
    Fraction,
    PurePath,
    range,
    re.Pattern,
    enum.Enum,
)
_IMMUTABLE_LIBRARY_MODULES: frozenset[str] = frozenset({"typing", "types", "builtins"})
_SKIPPED_FUNCTION_ATTRIBUTES: frozenset[str] = frozenset({"__sqlbuild_rule__", "__wrapped__"})


def rule_namespaces(rules: Iterable[object]) -> tuple[dict[str, object], ...]:
    """Return the module globals of every loaded custom-rule check."""

    namespaces: dict[int, dict[str, object]] = {}
    for check in rules:
        module_globals: object = getattr(check, "__globals__", None)
        if isinstance(module_globals, dict):
            namespaces.setdefault(id(module_globals), module_globals)
    return tuple(namespaces.values())


def module_state_token(*, namespaces: tuple[dict[str, object], ...], rules_root: Path) -> str:
    """Fingerprint every mutable value reachable from rule-module globals."""

    walker: _StateWalker = _StateWalker(rules_root=f"{rules_root.resolve()}{os.sep}")
    for namespace in namespaces:
        walker.visit_namespace(namespace)
    return walker.digest.hexdigest()


class _StateWalker:
    def __init__(self, *, rules_root: str) -> None:
        self.digest: Any = hashlib.sha256()
        self._rules_root: str = rules_root
        self._namespaces: set[int] = set()
        self._module_names: set[str] = set()
        self._visited: dict[int, int] = {}
        self._nodes: int = 0

    def visit_namespace(self, namespace: dict[str, object]) -> None:
        if id(namespace) in self._namespaces:
            return
        self._namespaces.add(id(namespace))
        name: object = namespace.get("__name__")
        self._module_names.add(str(name))
        self.emit(f"namespace:{name}")
        for key, value in sorted(namespace.items(), key=lambda item: item[0]):
            if key.startswith("__") and key.endswith("__"):
                continue
            self.emit(f"name:{key}")
            self.visit(value)

    def _owned_code(self, function: FunctionType) -> bool:
        return function.__code__.co_filename.startswith(self._rules_root)

    def emit(self, text: str) -> None:
        self.digest.update(text.encode())
        self.digest.update(b"\0")

    def visit(self, value: object) -> None:
        self._nodes += 1
        if self._nodes > _MAX_STATE_NODES:
            raise OpaqueModuleStateError("custom rule module state is too large to observe")
        if isinstance(value, _ATOMIC_TYPES) and not isinstance(value, (list, dict, set)):
            self.emit(f"atom:{type(value).__qualname__}:{value!r}")
            return
        identity: int = id(value)
        seen: int | None = self._visited.get(identity)
        if seen is not None:
            self.emit(f"ref:{seen}")
            return
        self._visited[identity] = len(self._visited)
        self.emit(f"object:{identity}:{type(value).__qualname__}")
        self._visit_structure(value)

    def _visit_structure(self, value: object) -> None:
        if isinstance(value, ModuleType):
            location: object = getattr(value, "__file__", None)
            if isinstance(location, str) and location.startswith(self._rules_root):
                self.visit_namespace(vars(value))
            else:
                self.emit(f"module:{value.__name__}")
        elif isinstance(value, dict):
            self._visit_mapping(cast(dict[object, object], value))
        elif isinstance(value, (list, tuple, deque)):
            self.emit(f"len:{len(value)}")
            for item in value:
                self.visit(item)
        elif isinstance(value, (set, frozenset)):
            self.emit(f"len:{len(value)}")
            tokens: list[str] = sorted(_atomic_text(item) for item in value)
            for token in tokens:
                self.emit(token)
        elif isinstance(value, FunctionType):
            self._visit_function(value)
        elif isinstance(value, MethodType):
            self.visit(value.__func__)
            self.visit(value.__self__)
        elif isinstance(value, type):
            self._visit_type(value)
        elif hasattr(value, "cache_info") and hasattr(value, "__wrapped__"):
            cached: Any = cast(Any, value)
            self.emit(f"cache:{cached.cache_info().currsize}")
            self.visit(cached.__wrapped__)
        elif isinstance(value, BuiltinFunctionType):
            self.emit(f"builtin:{getattr(value, '__module__', '')}:{value.__qualname__}")
        else:
            self._visit_instance(value)

    def _visit_mapping(self, value: dict[object, object]) -> None:
        self.emit(f"len:{len(value)}")
        factory: object = getattr(value, "default_factory", None)
        if factory is not None:
            self.visit(factory)
        for key, item in value.items():
            self.visit(key)
            self.visit(item)

    def _visit_function(self, value: FunctionType) -> None:
        if not self._owned_code(value):
            self.emit(f"function:{value.__module__}:{value.__qualname__}")
            return
        self.visit_namespace(value.__globals__)
        self.visit(value.__defaults__)
        self.visit(value.__kwdefaults__)
        for name, item in sorted(vars(value).items(), key=lambda entry: entry[0]):
            if name in _SKIPPED_FUNCTION_ATTRIBUTES:
                continue
            self.emit(f"attribute:{name}")
            self.visit(item)
        for cell in value.__closure__ or ():
            try:
                contents: object = cell.cell_contents
            except ValueError:
                self.emit("empty-cell")
                continue
            self.visit(contents)

    def _visit_type(self, value: type) -> None:
        owned: bool = value.__module__ in self._module_names or any(
            isinstance(item, FunctionType) and self._owned_code(item)
            for item in vars(value).values()
        )
        if not owned:
            self.emit(f"type:{value.__module__}:{value.__qualname__}")
            return
        for name, item in sorted(vars(value).items(), key=lambda entry: entry[0]):
            if name.startswith("__") and name.endswith("__"):
                continue
            self.emit(f"attribute:{name}")
            self.visit(item)

    def _visit_instance(self, value: object) -> None:
        state: dict[str, object] = {}
        attributes: object = getattr(value, "__dict__", None)
        if isinstance(attributes, dict):
            state.update(attributes)
        for owner in type(value).__mro__:
            for slot in getattr(owner, "__slots__", ()):
                if isinstance(slot, str) and hasattr(value, slot):
                    state[slot] = getattr(value, slot)
        if not state and type(value).__module__ not in self._module_names:
            if _is_immutable_library_value(value):
                self.emit(f"value:{type(value).__module__}:{type(value).__qualname__}")
                return
            raise OpaqueModuleStateError(
                f"custom rule module state holds an opaque {type(value).__qualname__}"
            )
        for name, item in sorted(state.items(), key=lambda entry: entry[0]):
            self.emit(f"attribute:{name}")
            self.visit(item)


def _atomic_text(value: object) -> str:
    if isinstance(value, _ATOMIC_TYPES):
        return f"{type(value).__qualname__}:{value!r}"
    if isinstance(value, tuple):
        return "(" + ",".join(_atomic_text(item) for item in value) + ")"
    raise OpaqueModuleStateError(
        f"custom rule module state holds an unhashable-order {type(value).__qualname__}"
    )


def _is_immutable_library_value(value: object) -> bool:
    return (
        isinstance(value, (staticmethod, classmethod, property))
        or callable(value)
        or type(value).__module__ in _IMMUTABLE_LIBRARY_MODULES
    )
