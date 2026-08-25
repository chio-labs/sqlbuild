from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlbuild.spec.contracts.types import SourceFreshnessValueKind


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
class ReadLatestSourceFreshnessRendererTestCase:
    description: str
    expected_executed_sql: str


@dataclass(frozen=True)
class WriteSourceFreshnessIndexTestCase:
    description: str
    expected_index_sql: str
    expected_insert_prefix: str
    expected_statement_count: int
    expected_values_separator: str


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
    freshness_filter: str | None = None
    expected_filter_fragment: str | None = None
    unexpected_sql_fragment: str | None = None


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
class DirectSourceFreshnessPlanningTestCase:
    description: str
    previous_data_version: str | None
    current_query: str
    expected_changed_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class DirectSourceFreshnessLagToleranceTestCase:
    description: str
    current_query: str
    expected_changed_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class DirectSourceFreshnessAgePolicyTestCase:
    description: str
    current_query: str
    warn_after: str | None
    error_after: str | None
    value_kind: SourceFreshnessValueKind
    expected_age_status: str
    observed_at: datetime = datetime(2026, 1, 15, 12, 0, 0)


@dataclass(frozen=True)
class DirectSourceFreshnessUnknownTestCase:
    description: str
    expected_unknown_source_names: tuple[str, ...]


@dataclass(frozen=True)
class DirectSourceFreshnessAdapterDefaultTestCase:
    description: str
    expected_changed_count: int
    expected_observed_count: int
    expected_batch_call_count: int


@dataclass(frozen=True)
class DirectSourceFreshnessManagedSkipTestCase:
    description: str
    expected_observed_count: int
    expected_unknown_source_names: tuple[str, ...]


@dataclass(frozen=True)
class DirectSourceFreshnessMultiSchemaTestCase:
    description: str
    expected_previous_count: int
    expected_unchanged_count: int


@dataclass(frozen=True)
class DirectSourceFreshnessDuplicateSchemaTestCase:
    description: str
    expected_previous_data_version: str
    expected_changed_count: int


@dataclass(frozen=True)
class DirectSourceFreshnessPropagationTestCase:
    description: str
    changed_source_names: tuple[str, ...]
    unknown_source_names: tuple[str, ...]
    downstream_edges: dict[str, tuple[str, ...]]
    expected_stale_model_names: frozenset[str]
    expected_changed_source_model_names: dict[str, frozenset[str]]
    expected_unknown_source_model_names: dict[str, frozenset[str]]
    error_source_names: tuple[str, ...] = ()
    expected_blocked_model_names: frozenset[str] = frozenset()
    expected_error_source_model_names: dict[str, frozenset[str]] | None = None


@dataclass(frozen=True)
class SharedSourceFreshnessExpressionSubqueryTestCase:
    description: str
    expression: str
    column: str
    expected_sql_fragment: str


@dataclass(frozen=True)
class DirectSourceFreshnessExpressionTestCase:
    description: str
    expression: str
    column: str
    expected_data_version: str
