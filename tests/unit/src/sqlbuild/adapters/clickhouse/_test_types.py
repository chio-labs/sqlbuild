from dataclasses import dataclass


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
