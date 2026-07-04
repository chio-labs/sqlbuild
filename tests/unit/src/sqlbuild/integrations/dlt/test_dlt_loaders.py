"""Unit tests for synthetic dlt loader discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.integrations.dlt.main.loaders import build_dlt_loader_functions
from sqlbuild.integrations.dlt.models import DltResourceConfig, DltSourceConfig
from sqlbuild.spec.models.source import IntegrationLoaderConfig, SourceEntry
from tests.unit.src.sqlbuild.integrations.dlt._test_types import DltLoaderDiscoveryTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DltLoaderDiscoveryTestCase(
            description="builds deterministic synthetic loader",
            expected_loader_names=("raw_orders",),
            expected_relative_path="sources/raw.yml",
            expected_function_name="raw_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dlt_source_when_building_loader_functions_then_name_is_deterministic(
    test_case: DltLoaderDiscoveryTestCase,
) -> None:
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("sources/raw.yml"),
        relative_path=Path("sources/raw.yml"),
        contents="",
        source_entries=(
            SourceEntry(
                name="raw_orders",
                loader="raw_orders",
                integration_loader=IntegrationLoaderConfig(
                    kind="dlt",
                    config=DltSourceConfig(
                        source_type="sql_database",
                        config={"credentials": "duckdb:///source.duckdb"},
                        destination={},
                        resource=DltResourceConfig(
                            name="raw_orders", dlt_name="orders", raw_config={}
                        ),
                        group_index=0,
                    ),
                ),
            ),
        ),
    )

    loaders: tuple[DiscoveredLoaderFunction, ...] = build_dlt_loader_functions((source_file,))

    assert tuple(loader.name for loader in loaders) == test_case.expected_loader_names
    assert loaders[0].relative_path == Path(test_case.expected_relative_path)
    loader_function: Any = cast(Any, loaders[0].function)
    assert loader_function.__name__ == test_case.expected_function_name
