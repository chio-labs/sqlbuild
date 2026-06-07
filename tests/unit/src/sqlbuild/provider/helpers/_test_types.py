"""Test types for provider session helper tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildProviderSessionTestCase:
    description: str
    provider_name: str
    expected_first_events: tuple[str, ...]
    expected_second_events: tuple[str, ...]


@dataclass(frozen=True)
class ProviderInjectionTestCase:
    description: str
    function: Callable[..., object]
    expected_result: object


@dataclass(frozen=True)
class ProviderInjectionLabelTestCase:
    description: str
    function: Callable[..., object]
    expected_label: str


@dataclass(frozen=True)
class ProviderInjectionErrorTestCase:
    description: str
    function: Callable[..., object]
    expected_error_fragment: str
