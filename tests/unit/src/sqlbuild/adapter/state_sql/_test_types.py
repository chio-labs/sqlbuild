from dataclasses import dataclass


@dataclass(frozen=True)
class StateSqlGoldenTestCase:
    description: str
    expected_sql: str
