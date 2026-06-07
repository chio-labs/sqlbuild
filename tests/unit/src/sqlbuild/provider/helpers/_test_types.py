"""Test types for provider session helper tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildProviderSessionTestCase:
    description: str
    provider_name: str
    expected_first_events: tuple[str, ...]
    expected_second_events: tuple[str, ...]
