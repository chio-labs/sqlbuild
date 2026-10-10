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


@dataclass(frozen=True)
class JsonReportTextTestCase:
    """One report value and the text the shipped encoders wrote for it."""

    description: str
    report: dict[object, object]
    expected_text: str


@dataclass(frozen=True)
class JsonReportErrorTestCase:
    """One report value the shipped encoder rejected, and its error message."""

    description: str
    report: dict[object, object]
    orjson_only: bool
    expected_message: str


@dataclass(frozen=True)
class CliJsonReportTestCase:
    """One compile of the surrogate project and the report text or error it produces."""

    description: str
    args: tuple[str, ...]
    expected_fragment: str


@dataclass(frozen=True)
class NestedReportTestCase:
    """A report nested `depth` lists deep under one key, beyond what `json.dumps` can write."""

    description: str
    depth: int
    expected_error: type[Exception]


@dataclass(frozen=True)
class NestedHookReportTestCase:
    """A real compile whose Python hook payload nests `depth` lists inside the report."""

    description: str
    depth: int
    expected_exit_code: int
