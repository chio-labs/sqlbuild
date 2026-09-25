from dataclasses import dataclass

from sqlbuild.spec.contracts.types import SourceFreshnessValueKind


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
    value_kind: SourceFreshnessValueKind | None
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
class SourceFreshnessStateErrorTestCase:
    description: str
    value_kind: str
    data_version: object
    expected_error_fragment: str
