"""Test case types for project input fingerprinting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class ProjectFingerprintTestCase:
    """One filesystem change and whether the project fingerprint must report it."""

    description: str
    change: Callable[[Path], None]
    expected_unchanged: bool


@dataclass(frozen=True)
class DigestCarryForwardTestCase:
    """A same-content change whose digest must be verified once and then carried forward."""

    description: str
    change: Callable[[Path], None]
    expected_verified: frozenset[str]
    expected_carried: frozenset[str]


@dataclass(frozen=True)
class RacyRewriteTestCase:
    """A rewrite inside one timestamp tick that leaves every stat field unchanged."""

    description: str
    racy: bool
    expected_unchanged: bool


@dataclass(frozen=True)
class LinkCycleTestCase:
    """A directory link that points back into the project."""

    description: str
    link_path: str
    expected_present: tuple[str, ...]
    expected_descended_prefix: str


@dataclass(frozen=True)
class RestampTestCase:
    """A stat change to a file stored without a digest, which must miss and queue hashing."""

    description: str
    change: Callable[[Path], None]
    expected_unchanged: bool
    expected_restamped: frozenset[str]


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
class SettingsDigestTestCase:
    """One change to the environment or settings files and whether the digest must move."""

    description: str
    change: Callable[[pytest.MonkeyPatch, Path], None]
    expected_changed: bool
