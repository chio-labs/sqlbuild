from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReadLatestSourceFreshnessTestCase:
    description: str
    rows: list[tuple[Any, ...]]
    expected_source_name: str
    expected_observed_at_iso: str


@dataclass(frozen=True)
class ReadLatestSourceFreshnessErrorTestCase:
    description: str
    read_error: Exception
    expected_message_fragment: str


@dataclass(frozen=True)
class SharedSourceFreshnessObservationTestCase:
    description: str
    adapter_observed_at: datetime | None
    fallback_observed_at: datetime
    expected_observed_at: datetime


@dataclass(frozen=True)
class SharedSourceFreshnessColumnSqlTestCase:
    description: str
    source_database: str | None
    source_schema: str | None
    source_table: str
    expected_sql_fragment: str


@dataclass(frozen=True)
class SharedSourceFreshnessObservationErrorTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SharedSourceFreshnessHashTestCase:
    description: str
    source_name: str
    strategy: str
    value_kind: str
    data_version: str
    observed_at: datetime
    later_observed_at: datetime
    expected_hash_changes_with_observed_at: bool
