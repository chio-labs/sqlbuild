"""Test types for CLI preview workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewCliTestCase:
    description: str
    scene: str
    arguments: tuple[str, ...]
    expected_return_code: int
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
