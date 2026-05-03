"""Planner domain models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.planner.types import SelectorKind


@dataclass(frozen=True)
class ParsedSelector:
    """One parsed selector token before graph resolution."""

    kind: SelectorKind
    value: str
    upstream: bool = False
    downstream: bool = False
