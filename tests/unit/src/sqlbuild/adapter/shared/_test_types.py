from dataclasses import dataclass

from sqlbuild.adapter.shared.type_normalization import NormalizedType


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
