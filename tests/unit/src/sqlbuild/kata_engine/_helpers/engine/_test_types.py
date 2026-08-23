"""Test case declarations for kata engine helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KataConfigErrorTestCase:
    description: str
    source: str
    expected_error_pattern: str


@dataclass(frozen=True)
class KataSelectionTestCase:
    description: str
    select: tuple[str, ...]
    ignore: tuple[str, ...]
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    body: str
    require_cacheable: bool
    expected_fault_codes: tuple[str, ...] = ()
    expected_error_pattern: str | None = None
    expected_cache_hits: int = 0
    minimum_custom_rule_cases: int = 0
    select: tuple[str, ...] = ("XSQBKT001",)
    enabled_by_default: bool = False
