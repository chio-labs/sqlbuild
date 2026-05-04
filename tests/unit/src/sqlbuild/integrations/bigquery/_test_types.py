from dataclasses import dataclass


@dataclass(frozen=True)
class BigQueryQueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_columns: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_truncated: bool


@dataclass(frozen=True)
class BigQueryRenderSchemaTestCase:
    description: str
    database: str | None
    schema: str
    location: str | None
    expected_sql: str


@dataclass(frozen=True)
class BigQueryRenderQualifiedNameTestCase:
    description: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified_name: str | None


@dataclass(frozen=True)
class BigQuerySchemaExistsTestCase:
    description: str
    missing_dataset: bool
    expected_exists: bool


@dataclass(frozen=True)
class BigQueryConnectErrorTestCase:
    description: str
    config: dict[str, object]
    expected_error_fragment: str
