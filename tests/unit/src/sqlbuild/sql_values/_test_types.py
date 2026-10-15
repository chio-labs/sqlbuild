from dataclasses import dataclass

from sqlbuild._native import SqlValueLimits, StateSqlValueType


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
class StateLiteralGoldenTestCase:
    description: str
    expected_literals: dict[str, str]


@dataclass(frozen=True)
class StateSqlGoldenTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class StateSqlTypeErrorTestCase:
    description: str
    column_type: StateSqlValueType
    expected_error: type[Exception]
