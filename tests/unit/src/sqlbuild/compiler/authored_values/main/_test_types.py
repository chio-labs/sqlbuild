from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoredValueTestCase:
    description: str
    parse: Callable[[object | None], object]
    raw_value: object | None
    expected_value: object


@dataclass(frozen=True)
class AuthoredValueErrorTestCase:
    description: str
    parse: Callable[[object | None], object]
    raw_value: object | None
    expected_message: str
