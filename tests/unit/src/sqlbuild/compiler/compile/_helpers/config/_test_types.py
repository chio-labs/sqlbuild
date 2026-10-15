from dataclasses import dataclass

from sqlbuild._native import MaterializationDefaultsConfig, TableType, TableTypeSource, TargetConfig


@dataclass(frozen=True)
class TableTypeResolutionTestCase:
    description: str
    header_values: dict[str, object]
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


@dataclass(frozen=True)
class AttachedColumnsTestCase:
    """A project's model configs and the schema columns attached to them."""

    description: str
    expected_columns: tuple[tuple[object, ...], ...]
