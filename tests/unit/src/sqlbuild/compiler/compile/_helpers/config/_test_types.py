from dataclasses import dataclass

from sqlbuild.spec.contracts.models import MaterializationDefaultsConfig, TargetConfig
from sqlbuild.spec.contracts.types import TableType, TableTypeSource


@dataclass(frozen=True)
class TableTypeResolutionTestCase:
    description: str
    model_value: object | None
    materialization_defaults: MaterializationDefaultsConfig
    target_config: TargetConfig | None
    expected_value: TableType
    expected_source: TableTypeSource
    expected_declared: bool


@dataclass(frozen=True)
class TableTypeResolutionErrorTestCase:
    description: str
    model_value: object
    expected_error_fragment: str


@dataclass(frozen=True)
class TableTypeValidationErrorTestCase:
    description: str
    materialized: str
    expected_error_fragment: str
    expected_declared: bool = True
