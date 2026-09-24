from __future__ import annotations

from dataclasses import dataclass

from scripts.dupscore.models import CloneAllowlistEntry


@dataclass(frozen=True)
class LoadConfigTestCase:
    description: str
    toml_text: str
    expected_surfaces: tuple[str, ...]
    expected_allowlisted_pair: tuple[str, str]
    expected_reason: str


@dataclass(frozen=True)
class MissingConfigTestCase:
    description: str
    expected_surfaces: tuple[str, ...]
    expected_allowlist_size: int


@dataclass(frozen=True)
class InvalidConfigTestCase:
    description: str
    toml_text: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CloneAllowlistTestCase:
    description: str
    toml_text: str
    expected_entries: tuple[CloneAllowlistEntry, ...]


@dataclass(frozen=True)
class ShippedConfigTestCase:
    description: str
    relative_path: str
    expected_pair_allowlist_size: int
    expected_clone_allowlist_size: int
