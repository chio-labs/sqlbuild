"""Test types for root-level public API tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSettingsTestCase:
    description: str
    env_name: str
    env_value: str
    expected_token: str
    expected_channel: str


@dataclass(frozen=True)
class ProviderSettingsErrorTestCase:
    description: str
    extra_field_name: str
    extra_field_value: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderNameTestCase:
    description: str
    provider_class_name: str
    expected_name: str


@dataclass(frozen=True)
class ExplicitProviderNameTestCase:
    description: str
    provider_name: str
    expected_name: str


@dataclass(frozen=True)
class InvalidExplicitProviderNameTestCase:
    description: str
    provider_class_name: str
    provider_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderLifecycleTestCase:
    description: str
    expected_setup_calls: int
    expected_teardown_calls: int
