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


@dataclass(frozen=True)
class EngineReuseDigestTestCase:
    """Two engine environments for one invocation and whether their reuse keys may match."""

    description: str
    first_environment: dict[str, str]
    second_environment: dict[str, str]
    expected_same_digest: bool


@dataclass(frozen=True)
class EngineReuseStoreTestCase:
    """One engine and the store directory that holds its compile reuse entry."""

    description: str
    engine: str
    expected_entry_directory: str
