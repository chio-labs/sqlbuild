"""Test case types for compiler stage captures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.frontier.types import CompilerStage


@dataclass(frozen=True)
class StageCaptureTestCase:
    """One value whose canonical capture must match an exact JSON-compatible shape."""

    description: str
    value: Callable[[], object]
    expected_capture: object


@dataclass(frozen=True)
class StageCaptureOrderTestCase:
    """Two values that differ only in ordering and whether their captures must be identical."""

    description: str
    first: Callable[[], object]
    second: Callable[[], object]
    expected_identical: bool


@dataclass(frozen=True)
class UnorderedAttributeTestCase:
    """Two fill orders for a memo map and an ordered map, and whether captures match."""

    description: str
    first_memo_keys: tuple[str, ...]
    second_memo_keys: tuple[str, ...]
    first_ordered_keys: tuple[str, ...]
    second_ordered_keys: tuple[str, ...]
    expected_identical: bool


@dataclass(frozen=True)
class OmittedFieldTestCase:
    """Dataclass fields left out of a capture, and the capture that remains."""

    description: str
    omitted: frozenset[str]
    expected_capture: object


@dataclass(frozen=True)
class FrontierCaptureTestCase:
    """Frontier stages compiled in order and the capture files they write."""

    description: str
    stages: tuple[CompilerStage, ...]
    expected_results: tuple[object, ...]
    expected_files: tuple[str, ...]


@dataclass(frozen=True)
class SharedCaptureTestCase:
    """A value with repeated large subtrees and how many distinct shared nodes its capture holds."""

    description: str
    value: Callable[[], object]
    expected_shared_nodes: int
