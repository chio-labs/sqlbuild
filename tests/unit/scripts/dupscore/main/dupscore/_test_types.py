from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliJsonTestCase:
    description: str
    arguments: tuple[str, ...]
    expected_total_clusters: int
    expected_unit_counts: dict[str, int]
    expected_cluster_keys: frozenset[str]
    expected_member_keys: frozenset[str]
    expected_progress_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliTextTestCase:
    description: str
    arguments: tuple[str, ...]
    expected_prefix: str
    expected_fragments: tuple[str, ...]
    absent_fragment: str


@dataclass(frozen=True)
class CliSinceTestCase:
    description: str
    new_files: dict[str, str]
    expected_fragments: tuple[str, ...]
    expected_new_markers: int


@dataclass(frozen=True)
class CliUsageErrorTestCase:
    description: str
    arguments: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class CliHelpTestCase:
    description: str
    expected_fragments: tuple[str, ...]
