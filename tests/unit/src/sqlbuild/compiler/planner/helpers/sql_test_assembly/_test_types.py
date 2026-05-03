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
    expected_sql_fragments: dict[str, str] = field(default_factory=dict)
    expected_warning_count: int = 0
    expected_warning_severity: WarningSeverity | None = None
    expected_error_fragment: str | None = None
    sql_body: str = ""
    expected_cte_bodies: dict[str, str] = field(default_factory=dict)
