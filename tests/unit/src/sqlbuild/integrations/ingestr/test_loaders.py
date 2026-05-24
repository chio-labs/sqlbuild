"""Unit tests for synthetic ingestr loader discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.integrations.ingestr.main.loaders import build_ingestr_loader_functions
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.models.source import IntegrationLoaderConfig, SourceEntry
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import (
    IngestrLoaderDiscoveryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrLoaderDiscoveryTestCase(
            description="builds deterministic synthetic loader",
            expected_loader_names=("ingestr__raw_orders",),
            expected_relative_path="sources/raw.yml",
            expected_function_name="ingestr__raw_orders",
        )
    ],
    ids=["builds deterministic synthetic loader"],
)
def test_given_ingestr_source_when_building_loader_functions_then_name_is_deterministic(
    test_case: IngestrLoaderDiscoveryTestCase,
) -> None:
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("sources/raw.yml"),
        relative_path=Path("sources/raw.yml"),
        contents="",
        source_entries=(
            SourceEntry(
                name="raw_orders",
                loader="ingestr__raw_orders",
                integration_loader=IntegrationLoaderConfig(
                    kind="ingestr",
                    config=IngestrSourceConfig(source_uri="stripe://token", source_table="charges"),
                ),
            ),
        ),
    )

    loaders: tuple[DiscoveredLoaderFunction, ...] = build_ingestr_loader_functions((source_file,))

    assert tuple(loader.name for loader in loaders) == test_case.expected_loader_names
    assert loaders[0].relative_path == Path(test_case.expected_relative_path)
    loader_function: Any = cast(Any, loaders[0].function)
    assert loader_function.__name__ == test_case.expected_function_name
