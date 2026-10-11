"""Helpers for model configuration reuse and native validation tests."""

import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    build_native_model_config,
    native_model_config_session,
    native_validation_error,
)
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileProjectInputs,
    ModelResourceNames,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
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


def compile_with_config_build_count(
    *,
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[CompileProjectInputs, int]:
    """Compile a project while counting its native model config builds."""

    build_counts: list[int] = [0]
    native_loop_type: type = _native.NativeModelLoop
    monkeypatch.setattr(
        _native,
        "NativeModelLoop",
        lambda *arguments: _ConfigCountingLoop(native_loop_type(*arguments), build_counts),
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return (
        build_compile_inputs(
            discovered_inputs=discovered_inputs,
            adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        ),
        build_counts[0],
    )


@dataclass(frozen=True)
class _ConfigCountingLoop:
    """The native model loop, adding up the model config builds it runs."""

    native_loop: Any
    build_counts: list[int]

    def run(self, *arguments: object) -> tuple[list[object], tuple[int, int, int]]:
        inputs, counts = self.native_loop.run(*arguments)
        self.build_counts[0] += counts[1]
        return inputs, counts


def compile_input_schema_columns(inputs: CompileProjectInputs) -> tuple[SchemaColumn, ...]:
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
        ((sys.version_info[0], sys.version_info[1]), unicodedata.unidata_version),
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
        names=ModelResourceNames(
            models={"orders"},
            seeds=set(),
            sources=set(),
            functions=set(),
            table_functions=set(),
            custom_materializations=frozenset(),
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
