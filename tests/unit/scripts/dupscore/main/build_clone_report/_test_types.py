from __future__ import annotations

from dataclasses import dataclass

from scripts.dupscore.models import CloneAllowlistEntry, ContractExemptionEntry


@dataclass(frozen=True)
class SeededCloneTestCase:
    description: str
    left_path: str
    right_path: str
    expected_category: str


@dataclass(frozen=True)
class ClusterShapeTestCase:
    description: str
    expected_languages: list[tuple[str, ...]]
    expected_sizes: list[int]


@dataclass(frozen=True)
class ExcludedUnitTestCase:
    description: str
    include_tests: bool
    name: str
    expected_reported: bool


@dataclass(frozen=True)
class ReportedPathTestCase:
    description: str
    include_tests: bool
    path: str
    expected_reported: bool


@dataclass(frozen=True)
class AllowlistTestCase:
    description: str
    entries: tuple[CloneAllowlistEntry, ...]
    expected_languages: list[tuple[str, ...]]
    expected_allowlisted_pairs: int


@dataclass(frozen=True)
class PathFilterTestCase:
    description: str
    path_globs: tuple[str, ...]
    expected_languages: list[tuple[str, ...]]


@dataclass(frozen=True)
class SinceFilterTestCase:
    description: str
    changed_files: dict[str, str]
    expected_changes: dict[str, str | None]


@dataclass(frozen=True)
class SinceUnchangedTestCase:
    description: str
    changed_files: dict[str, str]
    expected_cluster_count: int


@dataclass(frozen=True)
class ContractExemptionReportTestCase:
    description: str
    entries: tuple[ContractExemptionEntry, ...]
    expected_clusters: list[list[str]]
    expected_contract_exempt_members: int


@dataclass(frozen=True)
class ContractExemptionSinceTestCase:
    description: str
    changed_files: dict[str, str]
    expected_clusters: list[list[str]]
    expected_member_changes: dict[str, str | None]
