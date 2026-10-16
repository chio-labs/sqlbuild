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
class StartupInputsTestCase:
    """Import-path entries under a temporary root and the stamps they produce there."""

    description: str
    folders: tuple[str, ...]
    files: tuple[str, ...]
    path_entries: tuple[str, ...]
    expected_stamps: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class StartupInputsErrorTestCase:
    """An import-path entry whose stat fails with an error other than a missing file."""

    description: str
    files: tuple[str, ...]
    path_entry: str
    expected_error: type[OSError]
    expected_message: str
