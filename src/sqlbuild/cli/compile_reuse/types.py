"""Compile reuse outcome types."""

from __future__ import annotations

from enum import StrEnum


class CompileReuseOutcome(StrEnum):
    """How one compile invocation used the stored previous compile."""

    HIT = "hit"
    MISS = "miss"
    BYPASS = "bypass"
