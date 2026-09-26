"""Test case types for Rules performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RankingSettingsCase:
    description: str
    next_limit: int
    expected_exit: int
    expected_message: str


@dataclass(frozen=True)
class OverrideSettingsCase:
    description: str
    expected_exit: int = 1
    expected_message: str = "rules-model-override"


@dataclass(frozen=True)
class LiteralSettingsCase:
    description: str
    expected_code: str = "SQBRSQL044"


@dataclass(frozen=True)
class CteOutputSettingsCase:
    description: str
    expected_code: str = "SQBRSQL042"


@dataclass(frozen=True)
class GroupedRulesCase:
    description: str
    arguments: tuple[str, ...]
    result_key: str
    expected_rules: tuple[str, ...]
    configuration: str = ""


@dataclass(frozen=True)
class UnevaluatedRuleCase:
    description: str
    model_options: str = ""
    configuration: str = ""
    expected_exit: int = 1


@dataclass(frozen=True)
class UnevaluatedResourceCase:
    description: str
    path: str
    template: str
    expected_evaluated_models: int = 1
    expected_reason: str = "E_GUARD_FUNCTION_NESTING_DEPTH_EXCEEDED"
    adapter: str = "duckdb"


@dataclass(frozen=True)
class RulesPerformanceGuardTestCase:
    description: str
    model_count: int
    hard_ceiling_seconds: int
    expected_max_elapsed_seconds: float
    expected_returncode: int


@dataclass(frozen=True)
class UnusedCteContextTestCase:
    """Project whose framework context keeps a CTE reachable."""

    description: str
    files: dict[str, str]
    expected_returncode: int
    expected_finding_count: int
