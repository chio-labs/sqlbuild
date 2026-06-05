from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceFreshnessObservationTestCase:
    description: str
    setup_sql: tuple[str, ...]
    source_name: str
    table: str | None
    strategy: str
    value_kind: str
    expected_data_version: object
    column: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class SourceFreshnessObservationErrorTestCase:
    description: str
    setup_sql: tuple[str, ...]
    source_name: str
    table: str | None
    strategy: str
    value_kind: str | None
    expected_error_fragment: str
    column: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class UnsupportedTableFreshnessMetadataGuardTestCase:
    description: str
    source_name: str
    table: str
    expected_error_fragment: str
    expected_metadata_requested: bool


@dataclass(frozen=True)
class SourceFreshnessStateTestCase:
    description: str
    source_name: str
    strategy: str
    value_kind: str
    data_version: object
    observed_at: datetime
    expected_data_version: str
    expected_hash_changes_with_observed_at: bool


@dataclass(frozen=True)
class SourceFreshnessStateErrorTestCase:
    description: str
    value_kind: str
    data_version: object
    expected_error_fragment: str


@dataclass(frozen=True)
class SourceFreshnessRuntimeTestCase:
    description: str
    expected_record_sources: tuple[str, ...]
    expected_unknown_sources: tuple[str, ...]
    expected_preserved_sources: tuple[str, ...]
    expected_generated_sources: tuple[str, ...]


@dataclass(frozen=True)
class SourceFreshnessRuntimeLagToleranceTestCase:
    description: str
    current_data_version: str
    expected_record_data_version: str


@dataclass(frozen=True)
class VirtualSourceFreshnessCompatibilityTestCase:
    description: str
    expected_same_object: bool
