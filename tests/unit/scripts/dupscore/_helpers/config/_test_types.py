from __future__ import annotations

from dataclasses import dataclass


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
