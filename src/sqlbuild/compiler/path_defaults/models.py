"""Structured path-default selection models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathDefaultSelection:
    """Deterministic path-default matching result for one model path."""

    matched_keys: tuple[str, ...]
    selected_key: str | None
