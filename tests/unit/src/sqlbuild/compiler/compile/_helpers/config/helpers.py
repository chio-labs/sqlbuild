"""Helpers for model configuration reuse tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile._helpers.attachment import core as attachment_core
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileModelConfig, CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import SchemaColumn
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    DUCKDB_COMPILE_ADAPTER_CONTEXT,
)


def compile_with_config_build_count(
    *,
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[CompileProjectInputs, int]:
    """Compile a project while counting effective model configuration builds."""

    build_counts: list[int] = [0]
    original_build_model_config: Callable[..., CompileModelConfig] = (
        attachment_core.build_model_config
    )

    def counting_build_model_config(**kwargs: Any) -> CompileModelConfig:
        build_counts[0] += 1
        return original_build_model_config(**kwargs)

    monkeypatch.setattr(attachment_core, "build_model_config", counting_build_model_config)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return (
        build_compile_inputs(
            discovered_inputs=discovered_inputs,
            adapter_context=DUCKDB_COMPILE_ADAPTER_CONTEXT,
        ),
        build_counts[0],
    )


def compile_input_schema_columns(inputs: CompileProjectInputs) -> tuple[SchemaColumn, ...]:
    """Flatten attached schema columns in model input order."""

    columns: list[SchemaColumn] = []
    for model_input in inputs.model_inputs:
        columns.extend(getattr(model_input.schema_entry, "columns", ()))
    return tuple(columns)
