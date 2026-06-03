from dataclasses import dataclass


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
