"""Unit tests for synthetic dlt loader discovery."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild._native import DiscoveredProjectInputs, LoaderConnectionMode, discover_project_inputs
from tests.unit.src.sqlbuild.integrations.dlt._test_types import DltLoaderDiscoveryTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DltLoaderDiscoveryTestCase(
            description="builds deterministic synthetic loaders per resource",
            repo_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "sources/raw.yml": (
                    "dlt_sources:\n"
                    "  - type: sql_database\n"
                    "    config:\n"
                    '      credentials: "duckdb:///source.duckdb"\n'
                    "    resources:\n"
                    "      - name: raw_orders\n"
                    "        table: orders\n"
                    "      - name: raw_customers\n"
                    "        table: customers\n"
                ),
            },
            expected_loader_names=("raw_orders", "raw_customers"),
            expected_relative_paths=("sources/raw.yml", "sources/raw.yml"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dlt_source_when_discovering_inputs_then_loader_functions_are_deterministic(
    test_case: DltLoaderDiscoveryTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    assert tuple(loader.name for loader in inputs.loader_functions) == (
        test_case.expected_loader_names
    )
    assert tuple(str(loader.relative_path) for loader in inputs.loader_functions) == (
        test_case.expected_relative_paths
    )
    assert tuple(cast(Any, loader.function).__name__ for loader in inputs.loader_functions) == (
        test_case.expected_loader_names
    )
    assert {loader.connection_mode for loader in inputs.loader_functions} == {
        LoaderConnectionMode.EXTERNAL
    }
