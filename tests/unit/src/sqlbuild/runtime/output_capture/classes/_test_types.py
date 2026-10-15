"""Parameterized output capture test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingTestCase:
    """One deterministic text chunking case."""

    description: str
    text: str
    max_record_bytes: int
    expected_messages: tuple[str, ...]


@dataclass(frozen=True)
class OutputCaptureTestCase:
    """Named singleton case for one branch-free behavior test."""

    description: str
    expected_success: bool


@dataclass(frozen=True)
class InterpreterExitTestCase:
    """A script left delivering output when the interpreter finalizes, and its exit code."""

    description: str
    script: str
    expected_returncode: int
