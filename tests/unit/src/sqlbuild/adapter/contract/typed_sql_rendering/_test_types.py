from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter


@dataclass(frozen=True)
class AdapterTypedSqlRenderingTestCase:
    description: str
    adapter_factory: Callable[[], StrictAdapter]
    expected_string: str
    expected_true: str
    expected_false: str
    expected_integer: str
    expected_float: str
    expected_decimal: str
    expected_null: str
    expected_value_list: str
    expected_object: str


@dataclass(frozen=True)
class InvalidTypedArrayTestCase:
    description: str
    adapter_factory: Callable[[], StrictAdapter]
    raw_value: object
    expected_error: str


@dataclass(frozen=True)
class NativeArrayRenderingTestCase:
    description: str
    adapter_factory: Callable[[], StrictAdapter]
    raw_value: object
    expected_sql: str
