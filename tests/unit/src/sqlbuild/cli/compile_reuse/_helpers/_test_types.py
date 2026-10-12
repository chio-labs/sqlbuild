"""Test case types for project input fingerprinting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSettingsInputsTestCase:
    """One provider settings class and the external inputs its settings can read."""

    description: str
    settings_class: type
    expected_case_sensitive: bool = False
    expected_names: tuple[str, ...] = ()
    expected_prefixes: tuple[str, ...] = ()
    expected_env_file_names: tuple[str, ...] = ()
    expected_secrets_dir_names: tuple[str, ...] = ()
    expected_unsupported: bool = False
