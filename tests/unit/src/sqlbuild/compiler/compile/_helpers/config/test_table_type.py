from __future__ import annotations

import pytest

from sqlbuild._native import CompileModelConfig
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
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
from tests.unit.src.sqlbuild.compiler.compile._helpers.config.helpers import (
    build_config_natively,
    validate_natively,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeResolutionTestCase(
            description="model overrides materialization and target",
            header_values={"materialized": "table", "table_type": "transient"},
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
            header_values={"materialized": "table"},
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
            header_values={"materialized": "table", "table_type": "inherit"},
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
            header_values={"materialized": "table"},
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=TargetConfig(default_table_type=TableType.PERMANENT),
            expected_value=TableType.PERMANENT,
            expected_source=TableTypeSource.TARGET,
            expected_declared=True,
        ),
        TableTypeResolutionTestCase(
            description="undeclared value defaults transient",
            header_values={"materialized": "table"},
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=None,
            expected_value=TableType.TRANSIENT,
            expected_source=TableTypeSource.DEFAULT,
            expected_declared=False,
        ),
        TableTypeResolutionTestCase(
            description="target default does not apply to view",
            header_values={"materialized": "view"},
            materialization_defaults=MaterializationDefaultsConfig(),
            target_config=TargetConfig(default_table_type=TableType.PERMANENT),
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
    result: ResolvedTableType = build_config_natively(
        defaults=DefaultsConfig(),
        path_defaults={},
        matched_path_default=None,
        model_header_values=test_case.header_values,
        target_config=test_case.target_config,
        materialization_defaults=test_case.materialization_defaults,
    ).table_type

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
        build_config_natively(
            defaults=DefaultsConfig(),
            path_defaults={},
            matched_path_default=None,
            model_header_values={"materialized": "table", "table_type": test_case.model_value},
            target_config=None,
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
        TableTypeValidationErrorTestCase(
            description="ephemeral declaration is rejected",
            materialized="ephemeral",
            expected_error_fragment="not supported for materialization",
        ),
        TableTypeValidationErrorTestCase(
            description="seed declaration is rejected",
            materialized="seed",
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
        validate_natively(
            config=config,
            model_name="orders",
            custom_materialization_names=frozenset({test_case.materialized}),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
