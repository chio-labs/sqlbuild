"""Test case types for Rules performance guards."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


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
    rule: str = "SQBRSQL035"


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


@dataclass(frozen=True)
class HelperImportCase:
    description: str
    code: str
    rule_source: str
    helper_path: str
    helper_source: str
    expected_error: str


@dataclass(frozen=True)
class SqlRulePathParityCase:
    description: str
    files: dict[str, str]
    expected_findings: tuple[tuple[str, int, int, str], ...]
    expected_exit: int = 1


@dataclass(frozen=True)
class SqlQualityRuleCase:
    description: str
    upstream_header: str
    query_sql: str
    expected_findings: tuple[tuple[str, int], ...]
    expected_after_fix: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RankingKeyProofCase:
    description: str
    upstream_header: str
    upstream_sql: str
    query_sql: str
    expected_codes: tuple[str, ...]
    extra_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RankingSortDefaultCase:
    description: str
    order_by: str
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class FixableReportingCase:
    description: str
    summary_sql: str
    expected_fixability: tuple[tuple[str, bool], ...]
    expected_notes: tuple[tuple[str, tuple[str, ...]], ...]
    expected_help_fragments: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ConstantLiteralCase:
    description: str
    summary_sql: str
    expected_exit: int
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateLiteralCase:
    description: str
    literals: tuple[tuple[str, str], ...]
    expected_hints: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class RulesCacheEditCase:
    """One authored input edit applied after a warm compile with every rule selected."""

    description: str
    edit: Callable[[Path], None]
    expected_exit_code: int = 1
    expected_diagnostics_fragment: str = ""


@dataclass(frozen=True)
class SplitHostStateCase:
    """Custom rules sharing helper tables, one with cross-model state, across host processes."""

    description: str
    model_count: int
    selected_rules: tuple[str, ...]
    files: tuple[tuple[str, str], ...]
    expected_findings: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RulesEditChainCase:
    """A chain of authored edits, each compiled warm and compared with a cache-free compile."""

    description: str
    edits: tuple[RulesCacheEditCase, ...]
    expected_cold_codes: tuple[str, ...]
    expected_exit_code: int = 1


@dataclass(frozen=True)
class BrokenInvalidationChainCase:
    """An edit chain compiled with deliberately stale fact digests against a cache-free oracle."""

    description: str
    edits: tuple[RulesCacheEditCase, ...]
    stale_digests_sitecustomize: str
    expected_first_divergent_edit: str
