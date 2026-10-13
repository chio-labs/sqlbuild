from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HandoffTestCase:
    description: str
    args: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class TextReuseTestCase:
    description: str
    args: tuple[str, ...]
    expected_notice: bytes


@dataclass(frozen=True)
class JsonReuseTestCase:
    description: str
    args: tuple[str, ...]
    expected_hits: int


@dataclass(frozen=True)
class EditedProjectTestCase:
    description: str
    args: tuple[str, ...]
    old_text: str
    new_text: str
    expected_misses: int
    expected_fragment: str


@dataclass(frozen=True)
class SelectorFileTestCase:
    description: str
    selectors: str
    expected_records: int


@dataclass(frozen=True)
class PythonStartsTestCase:
    description: str
    args: tuple[str, ...]
    expected_python_starts: tuple[int, int, int]


@dataclass(frozen=True)
class ReuseFileMutationTestCase:
    description: str
    prepare: Callable[[Path], Path]
    expected_misses: int
    expected_fragment: str


@dataclass(frozen=True)
class ParserErrorTestCase:
    """One rejected command line and the coded error line `sqb` ends with."""

    description: str
    args: tuple[str, ...]
    expected_usage: bytes
    expected_error: bytes


@dataclass(frozen=True)
class SelectorCompileTestCase:
    """One compile command line and the model its JSON output names."""

    description: str
    args: tuple[str, ...]
    expected_model: bytes
