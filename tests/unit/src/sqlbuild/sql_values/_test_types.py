from dataclasses import dataclass

from sqlbuild.sql_values.models import SqlValueLimits


@dataclass(frozen=True)
class NormalizeSqlValueTestCase:
    description: str
    raw_value: object
    expected_kind: str
    expected_value: object
    explicit_type: str | None = None


@dataclass(frozen=True)
class NormalizeSqlValueErrorTestCase:
    description: str
    raw_value: object
    expected_error: str


@dataclass(frozen=True)
class SqlValueLimitTestCase:
    description: str
    raw_value: object
    limits: SqlValueLimits
    expected_error: str


@dataclass(frozen=True)
class SqlValueBehaviorTestCase:
    description: str
    expected_list_values: tuple[int, ...] = ()
    expected_identities_equal: bool = False


@dataclass(frozen=True)
class RenderedSqlValueLimitTestCase:
    description: str
    rendered_sql: str
    max_size: int
    expected_size: int


@dataclass(frozen=True)
class StateLiteralGoldenTestCase:
    description: str
    expected_literals: dict[str, str]
