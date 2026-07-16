from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteChainTestCase:
    description: str
    model_queries: dict[str, str]
    mock_ref_ctes: dict[str, str]
    mock_source_ctes: dict[str, str]
    helper_ctes: dict[str, str]
    expected_model_names: tuple[str, ...]
    expected_cte_bodies: dict[str, str]
    expected_results: dict[str, tuple[tuple[object, ...], ...]]
    expected_chain_length: int = 0


@dataclass(frozen=True)
class ExecuteMacroTestCase:
    description: str
    helper_ctes: dict[str, str]
    actual_sql: str
    expected_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
