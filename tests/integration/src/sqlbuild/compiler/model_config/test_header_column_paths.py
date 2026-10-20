"""Natively parsed MODEL header columns are reused whenever the built config keeps them."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.model_config._test_types import (
    HeaderColumnPathTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_config.helpers import header_column_paths


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderColumnPathTestCase(
            description="columns beside materialized, tags or a description",
            headers=(
                "materialized table, columns (order_id (type INTEGER))",
                'tags ["daily"], columns (order_id (type INTEGER))',
                'description "Orders.", columns (order_id (type INTEGER))',
            ),
            expected_native=3,
            expected_parsed=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_header_columns_when_building_model_inputs_then_native_columns_are_reused(
    test_case: HeaderColumnPathTestCase, tmp_path: Path
) -> None:
    paths: tuple[int, int] = header_column_paths(
        project_dir=tmp_path / "orders", headers=test_case.headers
    )

    assert paths == (test_case.expected_native, test_case.expected_parsed)
