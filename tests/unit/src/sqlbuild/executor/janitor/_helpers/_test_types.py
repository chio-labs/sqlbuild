from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ArchiveNameParseTestCase:
    description: str
    name: str
    expected_archived_at: datetime
    expected_logical_name: str


@dataclass(frozen=True)
class ArchiveNameRejectTestCase:
    description: str
    name: str
    expected_lookalike: bool


@dataclass(frozen=True)
class ArchiveNameBuildTestCase:
    description: str
    original_name: str
    archived_at: datetime
    identifier_limit: int
    expected_prefix: str
    expected_length: int
    expected_logical_name_is_original: bool
