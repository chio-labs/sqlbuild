"""Test case types for trusting artifacts a stored compile left."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifactTestCase:
    """A change to a stored artifact and whether its stored digest may still be trusted."""

    description: str
    change: Callable[[Path], None]
    written_contents: bytes
    expected_holds: bool
