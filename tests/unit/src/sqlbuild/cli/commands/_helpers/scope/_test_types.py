"""Scope output test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeOutputCase:
    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class ScopeDetailLevelCase:
    description: str
    verbose: bool
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScopeColourCase:
    description: str
    use_color: bool
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
