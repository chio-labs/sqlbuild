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
    macro_mocks: dict[str, str] = field(default_factory=dict)
    loaded_macro_outputs: dict[str, str] = field(default_factory=dict)
    function_locations: dict[str, str] = field(default_factory=dict)
    model_macro_source_queries: dict[str, str] = field(default_factory=dict)
    model_query_overrides: dict[str, str] = field(default_factory=dict)
    expected_sql_fragments: dict[str, str] = field(default_factory=dict)
    expected_warning_count: int = 0
    expected_warning_severity: WarningSeverity | None = None
    expected_error_fragments: tuple[str, ...] = field(default_factory=tuple)
    sql_body: str = ""
    expected_cte_bodies: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanMacroTestCase:
    description: str
    helper_ctes: dict[str, str]
    actual_sql: str
    expected_sql: str
    expected_actual_fragment: str
    expected_expected_fragment: str
