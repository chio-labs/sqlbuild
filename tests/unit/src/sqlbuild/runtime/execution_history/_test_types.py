"""Frozen cases for execution history public boundary tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportCase:
    description: str
    expected_forbidden_imports: tuple[str, ...]
