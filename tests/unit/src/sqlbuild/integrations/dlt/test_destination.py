"""Unit tests for dlt destination mapping."""

from __future__ import annotations

import pytest

from sqlbuild.integrations.dlt.helpers.destination import build_dlt_destination
from sqlbuild.integrations.dlt.models import DltDestinationConfig
from tests.unit.src.sqlbuild.integrations.dlt._test_types import DltDestinationTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DltDestinationTestCase(
            description="maps duckdb destination",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            dataset_name="raw",
            expected_destination_name="duckdb",
            expected_dataset_name="raw",
        )
    ],
    ids=["maps duckdb destination"],
)
def test_given_sqlbuild_connection_when_building_dlt_destination_then_maps_destination(
    test_case: DltDestinationTestCase,
) -> None:
    result: DltDestinationConfig = build_dlt_destination(
        adapter_name=test_case.adapter_name,
        connection_config=test_case.connection_config,
        dataset_name=test_case.dataset_name,
    )

    assert result.destination.destination_name == test_case.expected_destination_name
    assert result.dataset_name == test_case.expected_dataset_name
