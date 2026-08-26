"""Test case declarations for kata engine helpers."""

from dataclasses import dataclass

from sqlbuild.kata_engine.models import RuleExemption, RuleIgnore


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
class KataGuidanceTestCase:
    description: str
    expected_snippets: tuple[str, ...]


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    body: str
    require_cacheable: bool
    expected_fault_codes: tuple[str, ...] = ()
    expected_fault_lines: tuple[int, ...] = ()
    expected_error_pattern: str | None = None
    expected_cache_hits: int = 0
    minimum_custom_rule_cases: int = 0
    select: tuple[str, ...] = ("XSQBKT001",)
    enabled_by_default: bool = False


@dataclass(frozen=True)
class CustomRuleSuppressionTestCase:
    description: str
    rule_exceptions: tuple[RuleExemption, ...]
    rule_ignores: tuple[RuleIgnore, ...]
    expected_fault_codes: tuple[str, ...]


@dataclass(frozen=True)
class CustomRuleEvidenceTestCase:
    description: str
    test_source: str
    expected_count: int
    test_path: str = "tests/test_custom.py"


@dataclass(frozen=True)
class TypedConstantPayloadTestCase:
    description: str
    raw_value: object
    expected_value: object
    expected_type: str
