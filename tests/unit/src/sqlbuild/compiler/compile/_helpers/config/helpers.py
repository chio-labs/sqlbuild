"""Helpers for model configuration reuse and native validation tests."""

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import build_compile_inputs
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    build_native_model_config,
    native_model_config_session,
    native_validation_error,
)
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    MaterializationDefaultsConfig,
    ProjectConfig,
    SchemaColumn,
    TargetConfig,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    DUCKDB_COMPILE_ADAPTER_CONTEXT,
)

_NO_MATERIALIZATION_DEFAULTS: MaterializationDefaultsConfig = MaterializationDefaultsConfig()


def compile_with_native_config(*, project_dir: Path) -> CompileInputsView:
    """Compile a project's inputs through the native model config stage."""

    return build_compile_inputs(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
    )


def compile_input_schema_columns(inputs: CompileInputsView) -> tuple[SchemaColumn, ...]:
    """Flatten attached schema columns in model input order."""

    columns: list[SchemaColumn] = []
    for model_input in inputs.model_inputs:
        columns.extend(getattr(model_input.schema_entry, "columns", ()))
    return tuple(columns)


def validate_natively(  # noqa: PLR0913
    *,
    config: CompileModelConfig,
    model_name: str = "test_model",
    input_names: frozenset[str] = frozenset(),
    ref_count: int = 0,
    declared_columns: tuple[str, ...] | None = None,
    custom_materialization_names: frozenset[str] = frozenset(),
    query_sql: str = "SELECT 1",
    microbatch_concurrency: bool = False,
) -> None:
    """Run the native model validators, raising their first error.

    The model reads `ref_count` models, the first named from `input_names`; every one exists.
    """

    names: list[str] = sorted(input_names)[:ref_count]
    names.extend(f"upstream_{index}" for index in range(len(names), ref_count))
    validator: _native.NativeModelValidator = _native.NativeModelValidator(
        (set(names), set(), set(), set(), set()),
        set(custom_materialization_names),
        microbatch_concurrency,
    )
    outcome: int | _native.NativeConfigError | None = validator.validate(
        config.values,
        (model_name, query_sql, f"models/{model_name}.sql"),
        (
            [("ref", name, False) for name in names],
            declared_columns,
            config.time_travel_retention.unmanaged,
            config.table_type.declared,
        ),
    )
    assert not isinstance(outcome, int)
    for error in filter(None, (outcome,)):
        raise native_validation_error(error=error, values=config.values)


def build_config_natively(  # noqa: PLR0913
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
    target_config: TargetConfig | None,
    materialization_defaults: MaterializationDefaultsConfig = _NO_MATERIALIZATION_DEFAULTS,
    effective_target_name: str | None = None,
) -> CompileModelConfig:
    """Build the effective config of model `orders` with the native config builder."""

    session: NativeModelConfigSession = native_model_config_session(
        inputs=NativeModelConfigInputs(
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                defaults=defaults,
                path_defaults=path_defaults,
                materialization_defaults=materialization_defaults,
            ),
            target_config=target_config,
            effective_vars={},
            effective_target_name=effective_target_name,
            run_id="run_123",
            microbatch_concurrency=False,
        ),
        validator=_native.NativeModelValidator(
            ({"orders"}, set(), set(), set(), set()), set(), False
        ),
    )
    return build_native_model_config(
        session=session,
        model_file=DiscoveredSqlModelFile(
            file_path=Path("models/marts/orders.sql"),
            relative_path=Path("models/marts/orders.sql"),
            contents="SELECT 1",
            header_values=model_header_values,
            header_column_locations={},
            output_column_locations={},
            query_sql="SELECT 1",
        ),
        matched_path_default=matched_path_default,
    )
