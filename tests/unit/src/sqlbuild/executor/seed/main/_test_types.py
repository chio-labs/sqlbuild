"""Test case types for seed executor tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class SeedFingerprintFailureTestCase:
    description: str
    seed_name: str
    missing_file_path: Path
    expected_status: ExecutionStatus
    expected_fingerprint_table_exists: bool
