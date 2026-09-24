from dataclasses import dataclass, field

from sqlbuild.compiler.planner.types import WarningSeverity


@dataclass(frozen=True)
class PlanTestChainTestCase:
    description: str
    model_queries: dict[str, str]
    mock_ref_ctes: dict[str, str]
    mock_source_ctes: dict[str, str]
    helper_ctes: dict[str, str]
    expected_model_names: tuple[str, ...]
    expected_chain_length: int
    mock_seed_ctes: dict[str, str] = field(default_factory=dict)
    mock_dbt_ref_ctes: dict[str, str] = field(default_factory=dict)
    mock_table_function_ctes: dict[str, str] = field(default_factory=dict)
    macro_mocks: dict[str, str] = field(default_factory=dict)
    loaded_macro_outputs: dict[str, str] = field(default_factory=dict)
    function_locations: dict[str, str] = field(default_factory=dict)
    table_function_locations: dict[str, str] = field(default_factory=dict)
    model_macro_source_queries: dict[str, str] = field(default_factory=dict)
    model_query_overrides: dict[str, str] = field(default_factory=dict)
    expected_sql_fragments: dict[str, str] = field(default_factory=dict)
    unexpected_sql_fragments: dict[str, tuple[str, ...]] = field(default_factory=dict)
    expected_warning_count: int = 0
    expected_warning_severity: WarningSeverity | None = None
    expected_error_fragments: tuple[str, ...] = field(default_factory=tuple)
    sql_body: str = ""
    expected_cte_bodies: dict[str, str] = field(default_factory=dict)
    assertion_ctes: dict[str, str] = field(default_factory=dict)
    expected_assertion_fragments: dict[str, str] = field(default_factory=dict)
    expected_function_deps: tuple[str, ...] = ()
    expected_mock_table_function_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanMacroTestCase:
    description: str
    helper_ctes: dict[str, str]
    actual_sql: str
    expected_sql: str
    expected_actual_fragment: str
    expected_expected_fragment: str


@dataclass(frozen=True)
class AssertionChainCteErrorTestCase:
    description: str
    assertion_sql: str
    model_queries: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class RepeatedFixturePlanTestCase:
    description: str
    fixture_ids: tuple[int, ...]
    expected_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqlAnalysisDialectTestCase:
    description: str
    query_sql: str
    dialect: str
    expected_sql_fragment: str
    expected_absent_sql_fragment: str


@dataclass(frozen=True)
class NativePlanningDifferentialTestCase:
    description: str
    planning_case: PlanTestChainTestCase
    sql_analysis_enabled: bool = True
    expected_matches: bool = True


@dataclass(frozen=True)
class CursorWindowRenderingTestCase:
    description: str
    adapter_name: str
    cursor_type: str
    cursor_grain: str | None
    cursor_start: str | None
    cursor_end: str | None
    expected_sql: str
