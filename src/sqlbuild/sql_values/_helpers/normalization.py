"""Recursive implementation for typed SQL value normalization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.sql_values.constants import (
    MAX_SIGNED_64_BIT_INTEGER,
    MIN_SIGNED_64_BIT_INTEGER,
)
from sqlbuild.sql_values.exceptions import SqlValueValidationError
from sqlbuild.sql_values.models import AuthoredSqlSet, SqlLogicalType, SqlValue, SqlValueLimits
from sqlbuild.sql_values.types import SqlScalar, SqlValueKind

_SCALAR_KINDS: frozenset[SqlValueKind] = frozenset(
    {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.DECIMAL,
        SqlValueKind.NULL,
    }
)
_DEFAULT_SQL_VALUE_LIMITS: SqlValueLimits = SqlValueLimits()


@dataclass
class _NormalizationState:
    context: str
    limits: SqlValueLimits
    elements: int = 0
    size: int = 0

    def account(self, *, path: str, elements: int = 0, size: int = 0) -> None:
        self.elements += elements
        self.size += size
        if self.elements > self.limits.max_elements:
            raise SqlValueValidationError(
                f"{self.context}{path} exceeds the maximum element count "
                f"of {self.limits.max_elements}"
            )
        if self.size > self.limits.max_size:
            raise SqlValueValidationError(
                f"{self.context}{path} exceeds the maximum value size of "
                f"{self.limits.max_size} bytes"
            )


def normalize_sql_value(
    *,
    raw_value: object,
    context: str,
    explicit_type: str | None = None,
    limits: SqlValueLimits = _DEFAULT_SQL_VALUE_LIMITS,
) -> SqlValue:
    """Validate and normalize one authored value with contextual diagnostics."""

    state: _NormalizationState = _NormalizationState(context=context, limits=limits)
    return _normalize(
        raw_value=raw_value,
        path="",
        depth=1,
        state=state,
        explicit_type=explicit_type,
    )


def sql_value_identity(*, value: SqlValue) -> tuple[object, ...]:
    """Return typed canonical identity without Python's cross-type equality."""

    kind: SqlValueKind = value.kind
    if kind == SqlValueKind.DECIMAL:
        decimal_value: object = value.value
        if not isinstance(decimal_value, Decimal):
            raise SqlValueValidationError("typed decimal contains an invalid payload")
        return kind.value, decimal_value.normalize().as_tuple()
    if kind in _SCALAR_KINDS:
        return kind.value, value.value
    if kind in {SqlValueKind.LIST, SqlValueKind.SET}:
        items: tuple[SqlValue, ...] = cast(tuple[SqlValue, ...], value.value)
        return kind.value, tuple(sql_value_identity(value=item) for item in items)
    entries: tuple[tuple[str, SqlValue], ...] = cast(tuple[tuple[str, SqlValue], ...], value.value)
    return kind.value, tuple((key, sql_value_identity(value=item)) for key, item in entries)


def _normalize(
    *,
    raw_value: object,
    path: str,
    depth: int,
    state: _NormalizationState,
    explicit_type: str | None,
) -> SqlValue:
    if depth > state.limits.max_depth:
        raise SqlValueValidationError(
            f"{state.context}{path} exceeds the maximum nesting depth of {state.limits.max_depth}"
        )
    if explicit_type is not None:
        return _normalize_explicit_scalar(
            raw_value=raw_value, path=path, explicit_type=explicit_type, state=state
        )
    if raw_value is None:
        state.account(path=path, size=4)
        return _scalar(kind=SqlValueKind.NULL, value=None)
    if type(raw_value) is bool:
        state.account(path=path, size=5)
        return _scalar(kind=SqlValueKind.BOOLEAN, value=raw_value)
    if type(raw_value) is int:
        if not MIN_SIGNED_64_BIT_INTEGER <= raw_value <= MAX_SIGNED_64_BIT_INTEGER:
            raise SqlValueValidationError(
                f"{state.context}{path} integer {raw_value} is outside the signed 64-bit range"
            )
        state.account(path=path, size=len(str(raw_value)))
        return _scalar(kind=SqlValueKind.INTEGER, value=raw_value)
    if type(raw_value) is float:
        if not math.isfinite(raw_value):
            raise SqlValueValidationError(
                f"{state.context}{path} float must be finite; received {raw_value!r}"
            )
        normalized_float: float = 0.0 if raw_value == 0.0 else raw_value
        state.account(path=path, size=len(repr(normalized_float)))
        return _scalar(kind=SqlValueKind.FLOAT, value=normalized_float)
    if type(raw_value) is Decimal:
        if not raw_value.is_finite():
            raise SqlValueValidationError(
                f"{state.context}{path} decimal must be finite; received {raw_value!r}"
            )
        state.account(path=path, size=len(str(raw_value)))
        return _scalar(kind=SqlValueKind.DECIMAL, value=raw_value)
    if type(raw_value) is str:
        state.account(path=path, size=len(raw_value.encode("utf-8")) + 2)
        return _scalar(kind=SqlValueKind.STRING, value=raw_value)
    if type(raw_value) is list:
        return _normalize_collection(
            raw_values=tuple(raw_value), kind=SqlValueKind.LIST, path=path, depth=depth, state=state
        )
    if isinstance(raw_value, AuthoredSqlSet):
        return _normalize_collection(
            raw_values=raw_value.values,
            kind=SqlValueKind.SET,
            path=path,
            depth=depth,
            state=state,
        )
    if type(raw_value) is dict:
        return _normalize_object(
            raw_value=cast(dict[object, object], raw_value), path=path, depth=depth, state=state
        )
    raise SqlValueValidationError(
        f"{state.context}{path} has unsupported type {type(raw_value).__name__}; "
        "expected a scalar, list, set, or object"
    )


def _normalize_explicit_scalar(
    *, raw_value: object, path: str, explicit_type: str, state: _NormalizationState
) -> SqlValue:
    try:
        kind: SqlValueKind = SqlValueKind(explicit_type.lower())
    except ValueError as error:
        allowed: str = ", ".join(item.value for item in SqlValueKind if item in _SCALAR_KINDS)
        raise SqlValueValidationError(
            f"{state.context}{path} has unsupported explicit type '{explicit_type}'; "
            f"expected {allowed}"
        ) from error
    if kind not in _SCALAR_KINDS:
        raise SqlValueValidationError(
            f"{state.context}{path} explicit type '{explicit_type}' is not a scalar type"
        )
    if kind == SqlValueKind.DECIMAL:
        if type(raw_value) is not str:
            raise SqlValueValidationError(
                f"{state.context}{path} with type decimal requires a quoted decimal string; "
                f"received {type(raw_value).__name__}"
            )
        try:
            decimal_value: Decimal = Decimal(raw_value)
        except InvalidOperation as error:
            raise SqlValueValidationError(
                f"{state.context}{path} has invalid decimal value {raw_value!r}"
            ) from error
        if not decimal_value.is_finite():
            raise SqlValueValidationError(
                f"{state.context}{path} decimal must be finite; received {raw_value!r}"
            )
        state.account(path=path, size=len(raw_value))
        return _scalar(kind=kind, value=decimal_value)
    expected_types: dict[SqlValueKind, type[object]] = {
        SqlValueKind.STRING: str,
        SqlValueKind.INTEGER: int,
        SqlValueKind.BOOLEAN: bool,
        SqlValueKind.FLOAT: float,
        SqlValueKind.NULL: type(None),
    }
    expected_type: type[object] = expected_types[kind]
    valid: bool = type(raw_value) is expected_type
    if not valid:
        raise SqlValueValidationError(
            f"{state.context}{path} has type {type(raw_value).__name__}; expected {kind.value}"
        )
    return _normalize(raw_value=raw_value, path=path, depth=1, state=state, explicit_type=None)


def _normalize_collection(
    *,
    raw_values: tuple[object, ...],
    kind: SqlValueKind,
    path: str,
    depth: int,
    state: _NormalizationState,
) -> SqlValue:
    if not raw_values:
        raise SqlValueValidationError(
            f"{state.context}{path} {kind.value} must contain at least one value"
        )
    state.account(path=path, elements=len(raw_values), size=2 + len(raw_values))
    values: tuple[SqlValue, ...] = tuple(
        _normalize(
            raw_value=raw_value,
            path=f"{path}[{index}]",
            depth=depth + 1,
            state=state,
            explicit_type=None,
        )
        for index, raw_value in enumerate(raw_values)
    )
    element_type: SqlLogicalType = _infer_element_type(
        values=values, path=path, kind=kind, state=state
    )
    if kind == SqlValueKind.SET:
        seen: set[tuple[object, ...]] = set()
        for index, value in enumerate(values):
            identity: tuple[object, ...] = sql_value_identity(value=value)
            if identity in seen:
                raise SqlValueValidationError(
                    f"{state.context}{path} contains duplicate set value {value.value!r} "
                    f"at {path}[{index}]"
                )
            seen.add(identity)
        values = tuple(sorted(values, key=lambda value: repr(sql_value_identity(value=value))))
    return SqlValue(logical_type=SqlLogicalType(kind, element_type), value=values)


def _infer_element_type(
    *, values: tuple[SqlValue, ...], path: str, kind: SqlValueKind, state: _NormalizationState
) -> SqlLogicalType:
    expected: SqlLogicalType | None = next(
        (value.logical_type for value in values if value.kind != SqlValueKind.NULL), None
    )
    if expected is None:
        raise SqlValueValidationError(
            f"{state.context}{path} {kind.value} cannot infer an element type from only null values"
        )
    for index, value in enumerate(values):
        if value.kind != SqlValueKind.NULL and value.logical_type != expected:
            raise SqlValueValidationError(
                f"{state.context}{path}[{index}] has type {value.logical_type.display_name}; "
                f"expected {expected.display_name}"
            )
    return expected


def _normalize_object(
    *, raw_value: dict[object, object], path: str, depth: int, state: _NormalizationState
) -> SqlValue:
    state.account(path=path, elements=len(raw_value), size=2 + len(raw_value))
    entries: list[tuple[str, SqlValue]] = []
    for raw_key, item in raw_value.items():
        if type(raw_key) is not str:
            raise SqlValueValidationError(
                f"{state.context}{path} object key {raw_key!r} must be a string"
            )
        state.account(path=path, size=len(raw_key.encode("utf-8")) + 2)
        item_path: str = f"{path}.{raw_key}" if path else f".{raw_key}"
        entries.append(
            (
                raw_key,
                _normalize(
                    raw_value=item,
                    path=item_path,
                    depth=depth + 1,
                    state=state,
                    explicit_type=None,
                ),
            )
        )
    entries.sort(key=lambda entry: entry[0])
    return SqlValue(logical_type=SqlLogicalType(SqlValueKind.OBJECT), value=tuple(entries))


def _scalar(*, kind: SqlValueKind, value: SqlScalar) -> SqlValue:
    return SqlValue(logical_type=SqlLogicalType(kind), value=value)
