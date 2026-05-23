from dataclasses import dataclass

from sqlbuild.adapter.shared.type_normalization import NormalizedType
from sqlbuild.adapter.shared.types import LoaderLogicalType


@dataclass(frozen=True)
class TypeNormalizationTestCase:
    description: str
    dialect: str | None
    raw_type: str
    expected_type: NormalizedType


@dataclass(frozen=True)
class TypeEqualityTestCase:
    description: str
    dialect: str | None
    left_type: str
    right_type: str
    expected_equal: bool


@dataclass(frozen=True)
class NumericFamilyTestCase:
    description: str
    dialect: str | None
    raw_type: str
    expected_family: str | None


@dataclass(frozen=True)
class AdapterLoaderTypeMappingTestCase:
    description: str
    adapter_name: str
    expected_types: dict[LoaderLogicalType, str]


@dataclass(frozen=True)
class AdapterLoaderValueLiteralTestCase:
    description: str
    adapter_name: str
    value: object
    logical_type: LoaderLogicalType | None
    expected_literal: str


@dataclass(frozen=True)
class AdapterIdentifierRenderingTestCase:
    description: str
    adapter_name: str
    raw_identifier: str
    expected_identifier: str


@dataclass(frozen=True)
class AdapterLoaderRowsSelectTestCase:
    description: str
    adapter_name: str
    expected_fragments: tuple[str, ...]
    forbidden_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterLoaderRowsEmptySelectTestCase:
    description: str
    adapter_name: str
    expected_sql: str


@dataclass(frozen=True)
class AdapterSourceExpressionRenderingTestCase:
    description: str
    adapter_name: str
    expected_relation: str
    expected_cast_subquery: str
    expected_relation_cast_subquery: str
