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


@dataclass(frozen=True)
class StandardSourceFreshnessPlanningTestCase:
    description: str
    previous_data_version: str | None
    current_query: str
    expected_changed_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class StandardSourceFreshnessLagToleranceTestCase:
    description: str
    current_query: str
    expected_changed_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class StandardSourceFreshnessUnknownTestCase:
    description: str
    expected_unknown_source_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardSourceFreshnessAdapterDefaultTestCase:
    description: str
    expected_changed_count: int
    expected_observed_count: int


@dataclass(frozen=True)
class StandardSourceFreshnessManagedSkipTestCase:
    description: str
    expected_observed_count: int
    expected_unknown_source_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardSourceFreshnessMultiSchemaTestCase:
    description: str
    expected_previous_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class StandardSourceFreshnessPropagationTestCase:
    description: str
    changed_source_names: tuple[str, ...]
    unknown_source_names: tuple[str, ...]
    downstream_edges: dict[str, tuple[str, ...]]
    expected_stale_model_names: frozenset[str]
    expected_changed_source_model_names: dict[str, frozenset[str]]
    expected_unknown_source_model_names: dict[str, frozenset[str]]


@dataclass(frozen=True)
class StandardSourceFreshnessPlanningErrorTestCase:
    description: str
    expected_error_fragment: str
