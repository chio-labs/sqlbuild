from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FactCacheReadTestCase:
    """One read of a fact published for the ("orders", "SELECT 1") inputs."""

    description: str
    read_key_parts: tuple[str, ...]
    read_algorithm: str
    expected_hit: bool
    expected_metrics: tuple[int, int]


@dataclass(frozen=True)
class FactCacheCodeIdentityTestCase:
    """One change to the installed code that produced a published fact."""

    description: str
    next_code_identity: str
    expected_found_count: int


@dataclass(frozen=True)
class FactCacheCorruptionTestCase:
    """One way a persisted fact row can become untrustworthy."""

    description: str
    corrupt: Callable[[Path], None]
    expected_found_count: int
    expected_republished_hit: bool


@dataclass(frozen=True)
class FactCacheRetentionTestCase:
    """A sequence of (key parts, slot) publications and the rows that must remain."""

    description: str
    publications: tuple[tuple[tuple[str, ...], str], ...]
    stale_key_parts: tuple[str, ...]
    expected_slots: list[str]
    expected_stale_found_count: int


@dataclass(frozen=True)
class FactCacheNoPersistenceTestCase:
    """One invocation shape that must leave no fact database behind."""

    description: str
    expected_enabled: bool
    expected_database_files: list[Path]


@dataclass(frozen=True)
class FactCacheWriterErrorTestCase:
    """One SQLite error raised while publishing after an earlier fact was stored."""

    description: str
    error: Exception
    expected_earlier_found_count: int


@dataclass(frozen=True)
class FactCacheParameterLimitTestCase:
    """One SQLite bound-parameter limit and a publication larger than one statement allows."""

    description: str
    max_bound_parameters: int
    fact_count: int
