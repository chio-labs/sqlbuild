from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.config.model_validation import validate_table_type
from sqlbuild.compiler.compile._helpers.config.table_type import resolve_table_type
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.spec.contracts.models import (
    MaterializationDefaultsConfig,
    MaterializationRetentionDefaults,
    ResolvedTableType,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import TableType, TableTypeSource
from tests.unit.src.sqlbuild.compiler.compile._helpers.config._test_types import (
    TableTypeResolutionErrorTestCase,
    TableTypeResolutionTestCase,
    TableTypeValidationErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeResolutionTestCase(
            description="model overrides materialization and target",
            model_value="transient",
            materialization_defaults=MaterializationDefaultsConfig(
                table=MaterializationRetentionDefaults(table_type=TableType.PERMANENT)
            ),
            target_config=TargetConfig(default_table_type=TableType.PERMANENT),
            expected_value=TableType.TRANSIENT,
            expected_source=TableTypeSource.MODEL,
            expected_declared=True,
        ),
        TableTypeResolutionTestCase(
            description="materialization overrides target",
            model_value=None,
            materialization_defaults=MaterializationDefaultsConfig(
                table=MaterializationRetentionDefaults(table_type=TableType.TRANSIENT)
            ),
            target_config=TargetConfig(default_table_type=TableType.PERMANENT),
            expected_value=TableType.TRANSIENT,
            expected_source=TableTypeSource.MATERIALIZATION,
            expected_declared=True,
        ),
        TableTypeResolutionTestCase(
            description="inherit preserves materialization value",
            model_value="inherit",
            materialization_defaults=MaterializationDefaultsConfig(
                table=MaterializationRetentionDefaults(table_type=TableType.PERMANENT)
            ),
            target_config=TargetConfig(default_table_type=TableType.TRANSIENT),
            expected_value=TableType.PERMANENT,
            expected_source=TableTypeSource.MATERIALIZATION,
            expected_declared=True,
        ),
        TableTypeResolutionTestCase(
            description="target supplies value without overrides",
            model_value=None,
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=TargetConfig(default_table_type=TableType.PERMANENT),
            expected_value=TableType.PERMANENT,
            expected_source=TableTypeSource.TARGET,
            expected_declared=True,
        ),
        TableTypeResolutionTestCase(
            description="undeclared value defaults transient",
            model_value=None,
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=None,
            expected_value=TableType.TRANSIENT,
            expected_source=TableTypeSource.DEFAULT,
            expected_declared=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_layered_table_type_when_resolving_then_effective_value_tracks_source(
    test_case: TableTypeResolutionTestCase,
) -> None:
    result: ResolvedTableType = resolve_table_type(
        materialized="table",
        model_value=test_case.model_value,
        materialization_defaults=test_case.materialization_defaults,
        target_config=test_case.target_config,
        model_name="orders",
    )

    assert result.value is test_case.expected_value
    assert result.source is test_case.expected_source
    assert result.declared is test_case.expected_declared


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeResolutionErrorTestCase(
            description="invalid string is rejected",
            model_value="temporary",
            expected_error_fragment="permanent, transient, or inherit",
        ),
        TableTypeResolutionErrorTestCase(
            description="non-string is rejected",
            model_value=1,
            expected_error_fragment="permanent, transient, or inherit",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_model_table_type_when_resolving_then_raises_compile_error(
    test_case: TableTypeResolutionErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_table_type(
            materialized="table",
            model_value=test_case.model_value,
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=None,
            model_name="orders",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeValidationErrorTestCase(
            description="view declaration is rejected",
            materialized="view",
            expected_error_fragment="not valid for views",
        ),
        TableTypeValidationErrorTestCase(
            description="custom declaration is rejected",
            materialized="partition_tracked",
            expected_error_fragment="not supported for materialization",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_table_materialization_when_validating_table_type_then_rejects_declaration(
    test_case: TableTypeValidationErrorTestCase,
) -> None:
    config: CompileModelConfig = CompileModelConfig(
        values={"materialized": test_case.materialized},
        table_type=ResolvedTableType(
            value=TableType.PERMANENT,
            source=TableTypeSource.MODEL,
            declared=test_case.expected_declared,
        ),
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_table_type(config=config, model_name="orders")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
