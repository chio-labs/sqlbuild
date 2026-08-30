"""Tests for shared seed CSV null handling."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.main.normalize_seed_csv_value import normalize_seed_csv_value
from sqlbuild.spec.contracts.models import SeedCsvSettings
from tests.unit.src.sqlbuild.adapter.contract._helpers._test_types import (
    NormalizeSeedCsvValueTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeSeedCsvValueTestCase(
            description="default empty field becomes null",
            value="",
            column_name="horse_id",
            csv_settings=SeedCsvSettings(),
            expected_value=None,
        ),
        NormalizeSeedCsvValueTestCase(
            description="disabled default null handling preserves empty field",
            value="",
            column_name="horse_id",
            csv_settings=SeedCsvSettings(keep_default_na=False),
            expected_value="",
        ),
        NormalizeSeedCsvValueTestCase(
            description="explicit global null value remains active without defaults",
            value="N/A",
            column_name="horse_id",
            csv_settings=SeedCsvSettings(na_values=("N/A",), keep_default_na=False),
            expected_value=None,
        ),
        NormalizeSeedCsvValueTestCase(
            description="explicit column null value applies only to matching column",
            value="unknown",
            column_name="horse_id",
            csv_settings=SeedCsvSettings(na_values={"horse_id": ("unknown",)}),
            expected_value=None,
        ),
        NormalizeSeedCsvValueTestCase(
            description="ordinary field remains unchanged",
            value="506799",
            column_name="horse_id",
            csv_settings=SeedCsvSettings(),
            expected_value="506799",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_csv_field_when_normalizing_then_returns_expected_value(
    test_case: NormalizeSeedCsvValueTestCase,
) -> None:
    result: str | None = normalize_seed_csv_value(
        value=test_case.value,
        column_name=test_case.column_name,
        csv_settings=test_case.csv_settings,
    )

    assert result == test_case.expected_value
