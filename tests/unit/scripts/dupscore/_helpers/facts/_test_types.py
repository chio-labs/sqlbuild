from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractModulesTestCase:
    description: str
    sources: dict[str, str]
    expected_modules: tuple[str, ...]


@dataclass(frozen=True)
class ExtractCallsTestCase:
    description: str
    sources: dict[str, str]
    function_qualified_name: str
    expected_resolved_calls: tuple[str, ...]


@dataclass(frozen=True)
class ExtractFieldsTestCase:
    description: str
    sources: dict[str, str]
    class_qualified_name: str
    expected_field_names: tuple[str, ...]
