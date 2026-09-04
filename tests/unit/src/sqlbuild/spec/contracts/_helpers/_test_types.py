from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigValueSuccessTestCase:
    description: str
    getter: Callable[..., object]
    values: dict[str, object]
    key: str
    expected_value: object


@dataclass(frozen=True)
class ConfigValueErrorTestCase:
    description: str
    getter: Callable[..., object]
    key: str
    expected_type: str
    value: object
