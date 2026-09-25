"""Test case types for migration executor helper integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ArtifactNamingTestCase:
    description: str
    existing_relations: tuple[str, ...]
    now: datetime
    expected_stage_name: str
    expected_displaced_name: str
    expected_destination_exists: bool


@dataclass(frozen=True)
class CloneFallbackTestCase:
    description: str
    clone_statements: tuple[str, ...]
    refused_messages: tuple[str, ...]
    expected_transfer: str
    expected_stage_rows: int


@dataclass(frozen=True)
class CloneFailureTestCase:
    description: str
    clone_statements: tuple[str, ...]
    refused_messages: tuple[str, ...]
    expected_error_fragment: str
    expected_stage_exists: bool
