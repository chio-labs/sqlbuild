from dataclasses import dataclass


@dataclass(frozen=True)
class BuildComparisonSqlTestCase:
    description: str
    adapter_name: str
    expected_fragments: tuple[str, ...]
