from dataclasses import dataclass
from datetime import datetime

from sqlbuild.adapter.contract.models import RelationUsageReport


@dataclass(frozen=True)
class CanonicalTypeTestCase:
    description: str
    type_sql: str
    expected_type: str


@dataclass(frozen=True)
class NullableTypeTestCase:
    description: str
    type_sql: str
    expected_type: str


@dataclass(frozen=True)
class QuoteStringTestCase:
    description: str
    value: str
    expected_literal: str


@dataclass(frozen=True)
class ArtifactRelationTestCase:
    description: str
    relation: str
    expected_prefix: str
    expected_name_length: int


@dataclass(frozen=True)
class SnapshotCloseRewriteTestCase:
    description: str
    statement: str
    expected_close_select: str


@dataclass(frozen=True)
class UnsupportedSnapshotStatementTestCase:
    description: str
    statement: str
    expected_code: str


@dataclass(frozen=True)
class NullableOffsetWindowTestCase:
    description: str
    statement: str
    expected_statement: str


@dataclass(frozen=True)
class FinalSourceReadTestCase:
    description: str
    adapter_name: str
    expected_relation: str | None
    expected_code: str | None


@dataclass(frozen=True)
class TableLayoutTestCase:
    description: str
    layout: dict[str, object]
    expected_clauses: str


@dataclass(frozen=True)
class SessionSettingConflictTestCase:
    description: str
    settings: dict[str, object]
    expected_code: str
    expected_message: str


@dataclass(frozen=True)
class AliasQualifiedColumnsTestCase:
    description: str
    actual: tuple[str, ...]
    expected: tuple[str, ...]
    expected_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class KeyIdentifiersTestCase:
    description: str
    key_expressions: tuple[str, ...]
    expected_identifiers: frozenset[str]


@dataclass(frozen=True)
class ClickHouseRelationUsageTestCase:
    description: str
    relations: tuple[tuple[str, str], ...]
    rows: tuple[tuple[object, ...], ...]
    expected_names_sql: str
    expected_usages: tuple[tuple[str, tuple[str, ...], int, datetime], ...]


@dataclass(frozen=True)
class ClickHouseRelationUsageQueryTestCase:
    description: str
    window_seconds: int
    expected_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ClickHouseRelationUsageChunkTestCase:
    description: str
    relation_count: int
    expected_query_names: tuple[int, ...]


@dataclass(frozen=True)
class ClickHouseRelationUsageUncheckedTestCase:
    description: str
    log_queries: object
    errors: tuple[Exception, ...]
    expected_report: RelationUsageReport


@dataclass(frozen=True)
class ClickHouseRelationUsageFailureTestCase:
    description: str
    error: Exception
    expected_error_match: str
