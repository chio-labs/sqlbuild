from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotherDuckConnectionDatabaseTestCase:
    description: str
    config: dict[str, object]
    expected_database: str


@dataclass(frozen=True)
class MotherDuckAdapterDefaultsTestCase:
    description: str
    expected_default_schema: str
    expected_sql_analysis_dialect: str | None
