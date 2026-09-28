from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class BackgroundSqlTestPlanningTestCase:
    description: str
    enabled: bool
    expected_planner_calls: int
    expected_error: str | None = None


@dataclass(frozen=True)
class MigrationFingerprintCacheTestCase:
    description: str
    requests: tuple[tuple[str, dict[str, str], str], ...]
    expected_computations: int


@dataclass(frozen=True)
class PersistedMigrationFingerprintTestCase:
    description: str
    between_runs: Callable[[Path, pytest.MonkeyPatch], None]
    expected_second_run_computations: int
