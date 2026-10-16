from dataclasses import dataclass

from sqlbuild.adapter.contract.models import NormalizedType
from sqlbuild.compiler.lineage.types import InferredNullability


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
class NullabilityRuleTestCase:
    description: str
    args: tuple[InferredNullability, ...]
    expected_first_arg: InferredNullability
    expected_conditional: InferredNullability
    expected_safe_cast: InferredNullability


@dataclass(frozen=True)
class FirstArgIdentityTestCase:
    description: str
    argument: object
    expected_same_object: bool
