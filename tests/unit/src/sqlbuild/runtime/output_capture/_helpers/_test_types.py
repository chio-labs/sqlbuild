"""Parameterized text chunking test cases."""

from collections.abc import Callable
from dataclasses import dataclass

type ChunkTextFunction = Callable[..., tuple[str, ...]]


@dataclass(frozen=True)
class ChunkTextTestCase:
    """One exact chunk_text expectation."""

    description: str
    text: str
    max_bytes: int
    expected_chunks: tuple[str, ...]


@dataclass(frozen=True)
class ChunkTextErrorTestCase:
    """One input the stored chunk contract rejects."""

    description: str
    text: str
    max_bytes: int
    expected_error: type[Exception]


@dataclass(frozen=True)
class ChunkTextOracleTestCase:
    """One seeded random comparison against the reference implementation."""

    description: str
    seed: int
    max_bytes: int
    count: int
    expected_mismatch_count: int


@dataclass(frozen=True)
class ChunkTextPerformanceTestCase:
    """One large payload chunking time budget."""

    description: str
    unit: str
    payload_bytes: int
    max_bytes: int
    expected_max_seconds: float
