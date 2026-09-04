"""Tests for the loader destination parsing contract."""

from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.loader_destination_parts import loader_destination_parts
from sqlbuild.spec.contracts.models import LoaderDestinationParts
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    InvalidLoaderDestinationTestCase,
    LoaderDestinationPartsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        LoaderDestinationPartsTestCase(
            description="one part applies database and schema defaults",
            destination="orders",
            default_database="warehouse",
            default_schema="raw",
            expected_parts=LoaderDestinationParts("warehouse", "raw", "orders"),
        ),
        LoaderDestinationPartsTestCase(
            description="two parts override schema and retain database default",
            destination="staging.orders",
            default_database="warehouse",
            default_schema="raw",
            expected_parts=LoaderDestinationParts("warehouse", "staging", "orders"),
        ),
        LoaderDestinationPartsTestCase(
            description="three parts override all defaults",
            destination="archive.staging.orders",
            default_database="warehouse",
            default_schema="raw",
            expected_parts=LoaderDestinationParts("archive", "staging", "orders"),
        ),
        LoaderDestinationPartsTestCase(
            description="quoted parts remain unchanged",
            destination='"archive"."staging"."orders"',
            default_database=None,
            default_schema=None,
            expected_parts=LoaderDestinationParts('"archive"', '"staging"', '"orders"'),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_valid_destination_when_parsing_then_returns_qualified_parts(
    test_case: LoaderDestinationPartsTestCase,
) -> None:
    assert (
        loader_destination_parts(
            destination=test_case.destination,
            default_database=test_case.default_database,
            default_schema=test_case.default_schema,
        )
        == test_case.expected_parts
    )


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidLoaderDestinationTestCase(
            description="rejects empty string",
            destination="",
            expected_error_fragment="expected 1 to 3 non-empty dot-separated parts",
        ),
        InvalidLoaderDestinationTestCase(
            description="rejects leading empty part",
            destination=".orders",
            expected_error_fragment="expected 1 to 3 non-empty dot-separated parts",
        ),
        InvalidLoaderDestinationTestCase(
            description="rejects middle empty part",
            destination="raw..orders",
            expected_error_fragment="expected 1 to 3 non-empty dot-separated parts",
        ),
        InvalidLoaderDestinationTestCase(
            description="rejects trailing empty part",
            destination="raw.orders.",
            expected_error_fragment="expected 1 to 3 non-empty dot-separated parts",
        ),
        InvalidLoaderDestinationTestCase(
            description="rejects more than three parts",
            destination="a.b.c.d",
            expected_error_fragment="expected 1 to 3 non-empty dot-separated parts",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_destination_when_parsing_then_raises_clear_config_error(
    test_case: InvalidLoaderDestinationTestCase,
) -> None:
    with pytest.raises(SpecConfigError, match=test_case.expected_error_fragment):
        loader_destination_parts(
            destination=test_case.destination,
            default_database="warehouse",
            default_schema="raw",
        )
