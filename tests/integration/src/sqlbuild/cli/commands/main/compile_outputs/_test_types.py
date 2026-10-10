from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class CompileOutputsSequenceTestCase:
    """One engine's cached edit sequence and the native output work counted per step."""

    description: str
    engine: str
    expected_exit_codes: tuple[int, ...]
    expected_work: tuple[dict[str, int], ...]


@dataclass(frozen=True)
class PublicationFailureTestCase:
    """One engine's staged publication onto a path a directory blocks."""

    description: str
    engine: str
    expected_error: str
    expected_published_files: int


@dataclass(frozen=True)
class ReuseDisruptionTestCase:
    """One engine's stored compile disrupted between an unchanged rerun and the next compile."""

    description: str
    engine: str
    disrupt: Callable[[Path, pytest.MonkeyPatch], None]
    expected_reused: tuple[bool, ...]
    expected_slots: int
