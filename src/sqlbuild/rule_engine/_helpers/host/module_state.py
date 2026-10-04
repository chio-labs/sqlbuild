"""Detect custom-rule module state that one evaluation could leave for another."""

from __future__ import annotations

import enum
import hashlib
import os
import re
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict, deque
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from decimal import Decimal
from fractions import Fraction
from operator import itemgetter
from pathlib import Path, PurePath
from types import BuiltinFunctionType, CellType, FunctionType, MethodType, ModuleType
from typing import Any, cast

from sqlbuild.rule_engine.exceptions import OpaqueModuleStateError
from sqlbuild.rule_engine.models import ModuleStateFingerprint, ModuleStateTrace

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
_PLAIN_TYPES: frozenset[type] = frozenset({str, int, bytes})
_BUILTIN_ATOM_TYPES: frozenset[type] = frozenset(
    {type(None), bool, float, complex, bytearray, range, re.Pattern, Decimal}
)
_UNTRACED_TYPES: frozenset[type] = _PLAIN_TYPES | _BUILTIN_ATOM_TYPES
_BUILTIN_SEQUENCES: frozenset[type] = frozenset({tuple, list, deque})
_BUILTIN_MAPPINGS: frozenset[type] = frozenset({dict, defaultdict, OrderedDict})
_BUILTIN_SETS: frozenset[type] = frozenset({set, frozenset})
_BUILTIN_CONTAINERS: frozenset[type] = (
    _BUILTIN_SEQUENCES
    | _BUILTIN_MAPPINGS
    | _BUILTIN_SETS
    | {FunctionType, MethodType, BuiltinFunctionType, ModuleType, type}
)
_NAMESPACE: str = "namespace"
_REFERENCE: str = "ref"
_OBJECT: str = "object"
_ATOM: str = "atom"
_SET: str = "set"
_ITEMS: str = "items"
_PLAIN_ITEMS: str = "plain-items"
_MAPPING: str = "mapping"
_CELLS: str = "cells"
_ATTRIBUTES: str = "attributes"
_EMPTY_INSTANCE: str = "empty-instance"
_OWNED_MODULE: tuple[str] = ("owned-module",)
_OWNED_FUNCTION: tuple[str] = ("owned-function",)
_EMPTY_CELL: tuple[str] = ("empty-cell",)
_DESCENDED: tuple[str] = ("descended",)


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

    return module_state_fingerprint(
        namespaces=namespaces, rules_root=rules_root_prefix(rules_root)
    ).token


def rules_root_prefix(rules_root: Path) -> str:
    """Return the resolved path prefix that marks code and modules as owned by the project."""

    return f"{rules_root.resolve()}{os.sep}"


def module_state_fingerprint(
    *, namespaces: tuple[dict[str, object], ...], rules_root: str
) -> ModuleStateFingerprint:
    """Fingerprint rule-module state exactly and trace what the walk touched and decided."""

    walker: _StateWalker = _StateWalker(rules_root=rules_root)
    for namespace in namespaces:
        walker.visit_namespace(namespace)
    return ModuleStateFingerprint(
        token=walker.digest.hexdigest(),
        trace=ModuleStateTrace(
            touched=walker.touched,
            descended_types=frozenset(walker.descended_types),
            checked_instances=frozenset(walker.checked_instances),
        ),
    )


def module_state_snapshot(
    *,
    namespaces: Iterable[dict[str, object]],
    rules_root: str,
    trace: ModuleStateTrace,
    walks: int,
) -> list[object]:
    """Replay `walks` traced fingerprint walks at once and record what each would observe."""

    walker: _SnapshotWalker = _SnapshotWalker(
        rules_root=rules_root, trace=trace, max_nodes=_MAX_STATE_NODES * walks
    )
    for namespace in namespaces:
        walker.visit_namespace(namespace)
    return walker.observed


class _Walker(ABC):
    """Dispatch one reachable object to the branch every module-state walk takes for it."""

    def __init__(self, *, rules_root: str) -> None:
        self._rules_root: str = rules_root

    @abstractmethod
    def visit(self, value: object) -> None: ...

    def _visit_structure(self, value: object) -> None:
        if isinstance(value, ModuleType):
            location: object = getattr(value, "__file__", None)
            self._visit_module(
                module=value,
                owned=isinstance(location, str) and location.startswith(self._rules_root),
            )
        elif isinstance(value, dict):
            self._visit_mapping(cast(dict[object, object], value))
        elif isinstance(value, (list, tuple, deque)):
            self._visit_items(value)
        elif isinstance(value, (set, frozenset)):
            self._visit_set(value)
        elif isinstance(value, FunctionType):
            self._visit_function(value)
        elif isinstance(value, MethodType):
            self.visit(value.__func__)
            self.visit(value.__self__)
        elif isinstance(value, type):
            self._visit_type(value)
        elif hasattr(value, "cache_info") and hasattr(value, "__wrapped__"):
            self._visit_cache(value)
        elif isinstance(value, BuiltinFunctionType):
            self._visit_builtin(value)
        else:
            self._visit_instance(value)

    @abstractmethod
    def _visit_module(self, *, module: ModuleType, owned: bool) -> None: ...

    @abstractmethod
    def _visit_mapping(self, value: dict[object, object]) -> None: ...

    @abstractmethod
    def _visit_items(self, items: Collection[object]) -> None: ...

    @abstractmethod
    def _visit_set(self, value: Collection[object]) -> None: ...

    @abstractmethod
    def _visit_function(self, value: FunctionType) -> None: ...

    @abstractmethod
    def _visit_type(self, value: type) -> None: ...

    @abstractmethod
    def _visit_cache(self, value: Any) -> None: ...

    @abstractmethod
    def _visit_builtin(self, value: BuiltinFunctionType) -> None: ...

    @abstractmethod
    def _visit_instance(self, value: object) -> None: ...


class _StateWalker(_Walker):
    def __init__(self, *, rules_root: str) -> None:
        self.digest: Any = hashlib.sha256()
        self.module_names: set[str] = set()
        self.touched: dict[int, int] = {}
        self.descended_types: set[int] = set()
        self.checked_instances: set[int] = set()
        super().__init__(rules_root=rules_root)
        self._namespaces: set[int] = set()
        self._visited: dict[int, int] = {}
        self._nodes: int = 0

    def visit_namespace(self, namespace: dict[str, object]) -> None:
        if id(namespace) in self._namespaces:
            return
        self._namespaces.add(id(namespace))
        name: object = namespace.get("__name__")
        self.module_names.add(str(name))
        self.emit(f"namespace:{name}")
        for key, value in sorted(namespace.items(), key=lambda item: item[0]):
            if key.startswith("__") and key.endswith("__"):
                continue
            self.emit(f"name:{key}")
            self.visit(value)

    def _owned_code(self, function: FunctionType) -> bool:
        return function.__code__.co_filename.startswith(self._rules_root)

    def _trace(self, value: object) -> None:
        kind: type = type(value)
        if kind not in _UNTRACED_TYPES:
            self.touched[id(value)] = id(kind)

    def emit(self, text: str) -> None:
        self.digest.update(text.encode())
        self.digest.update(b"\0")

    def visit(self, value: object) -> None:
        self._nodes += 1
        if self._nodes > _MAX_STATE_NODES:
            raise OpaqueModuleStateError("custom rule module state is too large to observe")
        self._trace(value)
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

    def _visit_module(self, *, module: ModuleType, owned: bool) -> None:
        if owned:
            self.visit_namespace(vars(module))
        else:
            self.emit(f"module:{module.__name__}")

    def _visit_items(self, items: Collection[object]) -> None:
        self.emit(f"len:{len(items)}")
        for item in items:
            self.visit(item)

    def _visit_set(self, value: Collection[object]) -> None:
        self.emit(f"len:{len(value)}")
        tokens: list[str] = sorted(_atomic_text(value=item, observe=self._trace) for item in value)
        for token in tokens:
            self.emit(token)

    def _visit_cache(self, value: Any) -> None:
        self.emit(f"cache:{value.cache_info().currsize}")
        self.visit(value.__wrapped__)

    def _visit_builtin(self, value: BuiltinFunctionType) -> None:
        self.emit(f"builtin:{getattr(value, '__module__', '')}:{value.__qualname__}")

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
        owned: bool = value.__module__ in self.module_names or any(
            isinstance(item, FunctionType) and self._owned_code(item)
            for item in vars(value).values()
        )
        if not owned:
            self.emit(f"type:{value.__module__}:{value.__qualname__}")
            return
        self.descended_types.add(id(value))
        for name, item in sorted(vars(value).items(), key=lambda entry: entry[0]):
            if name.startswith("__") and name.endswith("__"):
                continue
            self.emit(f"attribute:{name}")
            self.visit(item)

    def _visit_instance(self, value: object) -> None:
        state: dict[str, object] = _instance_state(value)
        if not state and type(value).__module__ not in self.module_names:
            self.checked_instances.add(id(value))
            if _is_immutable_library_value(value):
                self.emit(f"value:{type(value).__module__}:{type(value).__qualname__}")
                return
            raise OpaqueModuleStateError(
                f"custom rule module state holds an opaque {type(value).__qualname__}"
            )
        for name, item in sorted(state.items(), key=lambda entry: entry[0]):
            self.emit(f"attribute:{name}")
            self.visit(item)


class _SnapshotWalker(_Walker):
    """Replay traced `_StateWalker` walks, recording what they observe without hashing it."""

    def __init__(self, *, rules_root: str, trace: ModuleStateTrace, max_nodes: int) -> None:
        super().__init__(rules_root=rules_root)
        self.observed: list[object] = []
        self._trace: ModuleStateTrace = trace
        self._touched: dict[int, int] = trace.touched
        self._max_nodes: int = max_nodes
        self._nodes: int = 0
        self._namespaces: set[int] = set()
        self._visited: dict[int, int] = {}

    def visit_namespace(self, namespace: dict[str, object]) -> None:
        identity: int = id(namespace)
        if identity in self._namespaces:
            return
        self._namespaces.add(identity)
        items: list[tuple[str, object]] = sorted(_named_items(namespace), key=itemgetter(0))
        self.observed.append(
            (
                _NAMESPACE,
                identity,
                f"namespace:{namespace.get('__name__')}",
                [key for key, _ in items],
            )
        )
        for _, value in items:
            self.visit(value)

    def visit(self, value: object) -> None:
        self._nodes += 1
        if self._nodes > self._max_nodes:
            raise OpaqueModuleStateError("custom rule module state is too large to snapshot")
        kind: type = type(value)
        if kind in _PLAIN_TYPES:
            self.observed.append(value)
            return
        if kind in _BUILTIN_ATOM_TYPES:
            self.observed.append(_atom(value))
            return
        if self._touched.get(id(value)) != id(kind):
            raise OpaqueModuleStateError("custom rule module state reached an untraced value")
        if (
            kind not in _BUILTIN_CONTAINERS
            and isinstance(value, _ATOMIC_TYPES)
            and not isinstance(value, (list, dict, set))
        ):
            self.observed.append(_atom(value))
            return
        identity: int = id(value)
        seen: int | None = self._visited.get(identity)
        if seen is not None:
            self.observed.append((_REFERENCE, seen))
            return
        self._visited[identity] = len(self._visited)
        self.observed.append((_OBJECT, identity, kind.__qualname__))
        if kind is tuple or kind is list:
            self._visit_items(cast(Collection[object], value))
        elif kind is dict:
            self._visit_mapping(cast(dict[object, object], value))
        elif kind is FunctionType:
            self._visit_function(cast(FunctionType, value))
        else:
            self._visit_structure(value)

    def _count(self, nodes: int) -> None:
        self._nodes += nodes
        if self._nodes > self._max_nodes:
            raise OpaqueModuleStateError("custom rule module state is too large to snapshot")

    def _require_traced(self, value: object) -> None:
        if self._trace.touched.get(id(value)) != id(type(value)):
            raise OpaqueModuleStateError("custom rule module state reached an untraced value")

    def _require_member_traced(self, value: object) -> None:
        if type(value) not in _UNTRACED_TYPES:
            self._require_traced(value)

    def _visit_module(self, *, module: ModuleType, owned: bool) -> None:
        if owned:
            self.observed.append(_OWNED_MODULE)
            self.visit_namespace(vars(module))
        else:
            self.observed.append(f"module:{module.__name__}")

    def _visit_cache(self, value: Any) -> None:
        self.observed.append(f"cache:{value.cache_info().currsize}")
        self.visit(value.__wrapped__)

    def _visit_builtin(self, value: BuiltinFunctionType) -> None:
        self.observed.append(f"builtin:{getattr(value, '__module__', '')}:{value.__qualname__}")

    def _visit_items(self, items: Collection[object]) -> None:
        if type(items) in _BUILTIN_SEQUENCES and _plain(items):
            self._count(len(items))
            self.observed.append((_PLAIN_ITEMS, list(items)))
            return
        self.observed.append((_ITEMS, len(items)))
        for item in items:
            self.visit(item)

    def _visit_mapping(self, value: dict[object, object]) -> None:
        size: int = len(value)
        factory: object = getattr(value, "default_factory", None)
        self.observed.append((_MAPPING, factory is None))
        if factory is not None:
            self.visit(factory)
        if type(value) in _BUILTIN_MAPPINGS and _plain(value.keys()) and _plain(value.values()):
            self._count(2 * size)
            self.observed.append(list(value.items()))
            return
        self.observed.append(size)
        for key, item in value.items():
            self.visit(key)
            self.visit(item)

    def _visit_set(self, value: Collection[object]) -> None:
        size: int = len(value)
        self._count(size)
        if type(value) in _BUILTIN_SETS and _plain(value):
            self.observed.append((_SET, set(value)))
            return
        self.observed.append(
            (
                _SET,
                size,
                sorted(
                    _atomic_text(value=item, observe=self._require_member_traced) for item in value
                ),
            )
        )

    def _visit_function(self, value: FunctionType) -> None:
        if not value.__code__.co_filename.startswith(self._rules_root):
            self.observed.append(f"function:{value.__module__}:{value.__qualname__}")
            return
        self.observed.append(_OWNED_FUNCTION)
        self.visit_namespace(value.__globals__)
        self.visit(value.__defaults__)
        self.visit(value.__kwdefaults__)
        self._visit_attributes(
            (name, item)
            for name, item in vars(value).items()
            if name not in _SKIPPED_FUNCTION_ATTRIBUTES
        )
        cells: tuple[CellType, ...] = value.__closure__ or ()
        self.observed.append((_CELLS, len(cells)))
        for cell in cells:
            try:
                contents: object = cell.cell_contents
            except ValueError:
                self.observed.append(_EMPTY_CELL)
                continue
            self.visit(contents)

    def _visit_type(self, value: type) -> None:
        owns_code: bool = any(
            type(item) is FunctionType
            and cast(FunctionType, item).__code__.co_filename.startswith(self._rules_root)
            for item in vars(value).values()
        )
        self.observed.append(f"type:{value.__module__}:{value.__qualname__}")
        self.observed.append(owns_code)
        if id(value) in self._trace.descended_types:
            self.observed.append(_DESCENDED)
            self._visit_attributes(_named_items(vars(value)))

    def _visit_instance(self, value: object) -> None:
        state: dict[str, object] = _instance_state(value)
        if not state:
            checked: bool = id(value) in self._trace.checked_instances
            self.observed.append(
                (
                    _EMPTY_INSTANCE,
                    f"{type(value).__module__}",
                    checked and _is_immutable_library_value(value),
                    checked,
                )
            )
            return
        self._visit_attributes(state.items())

    def _visit_attributes(self, attributes: Iterable[tuple[str, object]]) -> None:
        listed: list[tuple[str, object]] = list(attributes)
        if not _plain_names(name for name, _ in listed):
            raise OpaqueModuleStateError("custom rule module state has a non-string attribute")
        items: list[tuple[str, object]] = sorted(listed, key=itemgetter(0))
        self.observed.append((_ATTRIBUTES, [name for name, _ in items]))
        for _, item in items:
            self.visit(item)


def _plain(values: Iterable[object]) -> bool:
    return {*map(type, values)} <= _PLAIN_TYPES


def _plain_names(names: Iterable[object]) -> bool:
    return {*map(type, names)} <= {str}


def _atom(value: object) -> tuple[str, ...]:
    if type(value) is re.Pattern:
        pattern: re.Pattern[str] = cast(re.Pattern[str], value)
        return (_ATOM, "Pattern", pattern.pattern, str(pattern.flags))
    if type(value) is bool or value is None:
        return (_ATOM, repr(value))
    return (_ATOM, type(value).__qualname__, repr(value))


def _named_items(namespace: Mapping[str, object]) -> Iterator[tuple[str, object]]:
    for key, value in namespace.items():
        if type(key) is not str:
            raise OpaqueModuleStateError("custom rule module state has a non-string name")
        if not (key.startswith("__") and key.endswith("__")):
            yield key, value


def _instance_state(value: object) -> dict[str, object]:
    state: dict[str, object] = {}
    attributes: object = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        state.update(cast(dict[str, object], attributes))
    for owner in type(value).__mro__:
        for slot in getattr(owner, "__slots__", ()):
            if isinstance(slot, str) and hasattr(value, slot):
                state[slot] = getattr(value, slot)
    return state


def _atomic_text(*, value: object, observe: Callable[[object], None]) -> str:
    observe(value)
    if isinstance(value, _ATOMIC_TYPES):
        return f"{type(value).__qualname__}:{value!r}"
    if isinstance(value, tuple):
        return "(" + ",".join(_atomic_text(value=item, observe=observe) for item in value) + ")"
    raise OpaqueModuleStateError(
        f"custom rule module state holds an unhashable-order {type(value).__qualname__}"
    )


def _is_immutable_library_value(value: object) -> bool:
    return (
        isinstance(value, (staticmethod, classmethod, property))
        or callable(value)
        or type(value).__module__ in _IMMUTABLE_LIBRARY_MODULES
    )
