"""Test case types for Rules performance guards."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluatedPredicateCase:
    description: str
    sql: str
    expected_evaluated_models: int = 1


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
    extra_files: tuple[tuple[str, str], ...] = ()


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


@dataclass(frozen=True)
class HermeticRuleCase:
    description: str
    code: str
    files: tuple[tuple[str, str], ...]
    expected_rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class NonHermeticRuleCase:
    description: str
    code: str
    source: str
    expected_line: int
    expected_action: str


@dataclass(frozen=True)
class ScrubbedEnvironmentCase:
    description: str
    code: str
    source: str
    parent_environment: tuple[tuple[str, str], ...]
    expected_returncode: int
    expected_rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class HashSeedCase:
    description: str
    code: str
    names: tuple[str, ...]
    expected_hash_seed: str


@dataclass(frozen=True)
class ProjectTreeCacheCase:
    description: str
    code: str
    source: str
    policy_path: str
    added_model_path: str
    expected_paths_after_glob_change: tuple[str, ...]
    expected_minimum_cache_hits: int


@dataclass(frozen=True)
class ModuleStatementEditCase:
    description: str
    code: str
    source: str
    appended_statement: str
    expected_rule_codes_before_edit: tuple[str, ...]
    expected_rule_codes_after_edit: tuple[str, ...]


@dataclass(frozen=True)
class WorkingDirectoryCase:
    description: str
    code: str
    source: str
    invocation_directories: tuple[str, ...]
    expected_working_directory: str
