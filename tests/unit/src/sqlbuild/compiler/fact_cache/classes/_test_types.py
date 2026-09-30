from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FactCacheCorruptionTestCase:
    """One way a persisted fact row can become untrustworthy."""

    description: str
    corrupt: Callable[[Path], None]
