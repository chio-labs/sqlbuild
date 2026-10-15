"""Unit tests for synthetic ingestr loader discovery."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild._native import DiscoveredProjectInputs, LoaderConnectionMode, discover_project_inputs
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import (
    IngestrLoaderDiscoveryTestCase,
)

_INGESTR_SOURCES: str = (
    "sources:\n"
    "  - name: raw_orders\n"
    "    ingestr:\n"
    '      source_uri: "stripe://token"\n'
    "      source_table: charges\n"
    "  - name: plain_orders\n"
    "    schema: public\n"
    "    table: orders\n"
)
_DLT_SOURCES: str = (
    "dlt_sources:\n"
    "  - type: sql_database\n"
    "    config:\n"
    '      credentials: "duckdb:///source.duckdb"\n'
    "    resources:\n"
    "      - name: dlt_orders\n"
    "        table: orders\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrLoaderDiscoveryTestCase(
            description="builds deterministic synthetic loader",
            repo_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "sources/raw.yml": _INGESTR_SOURCES,
            },
            expected_loader_names=("ingestr__raw_orders",),
            expected_relative_paths=("sources/raw.yml",),
        ),
        IngestrLoaderDiscoveryTestCase(
            description="orders every ingestr loader before every dlt loader",
            repo_files={
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "duckdb"\n',
                "sources/a_dlt.yml": _DLT_SOURCES,
                "sources/b_raw.yml": _INGESTR_SOURCES,
            },
            expected_loader_names=("ingestr__raw_orders", "dlt_orders"),
            expected_relative_paths=("sources/b_raw.yml", "sources/a_dlt.yml"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ingestr_source_when_discovering_inputs_then_loader_functions_are_deterministic(
    test_case: IngestrLoaderDiscoveryTestCase,
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
