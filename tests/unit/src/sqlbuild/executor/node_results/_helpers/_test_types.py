from dataclasses import dataclass


@dataclass(frozen=True)
class NodeResultSqlTestCase:
    description: str
    expected_fragments: tuple[str, ...] = ()
    expected_sql: str = ""
