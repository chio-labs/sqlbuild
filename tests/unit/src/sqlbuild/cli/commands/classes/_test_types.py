from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliNamespaceDefaultTestCase:
    description: str
    attribute: str
    expected_value: object


@dataclass(frozen=True)
class CliNamespaceListIsolationTestCase:
    description: str
    attribute: str
    appended_value: str
    expected_first: list[str]
    expected_second: list[str]


@dataclass(frozen=True)
class CliNamespaceAssignmentTestCase:
    description: str
    attribute: str
    value: object
    expected_value: object


@dataclass(frozen=True)
class CliNamespaceMissingTestCase:
    description: str
    attribute: str
    expected_error_fragment: str
