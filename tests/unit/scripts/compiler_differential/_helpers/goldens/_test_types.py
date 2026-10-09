"""Test case types for the golden compile outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.compiler_differential.models import EngineRun


@dataclass(frozen=True)
class GoldenPathTestCase:
    """A corpus project name and where its golden lives, if anywhere."""

    description: str
    project: str
    expected_path: Path | None


@dataclass(frozen=True)
class GoldenPayloadTestCase:
    """One engine run and the masked golden it must produce."""

    description: str
    run: EngineRun
    masked_paths: tuple[str, ...]
    expected_payload: dict[str, object]


@dataclass(frozen=True)
class GoldenCheckTestCase:
    """A recorded golden, the runs checked against it, and the differences reported."""

    description: str
    project: str
    recorded: tuple[EngineRun, ...]
    checked: tuple[EngineRun, ...]
    expected_differences: tuple[tuple[str, tuple[str, str] | None], ...]
