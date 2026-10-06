from __future__ import annotations

import hashlib

import pytest

from sqlbuild.adapter.relations.main.fit_auxiliary_relation_name import (
    fit_auxiliary_relation_name,
)
from sqlbuild.errors.contracts.exceptions import SharedInputError
from tests.unit.src.sqlbuild.adapter.relations.main.fit_auxiliary_relation_name._test_types import (
    FitAuxiliaryRelationNameErrorTestCase,
    FitAuxiliaryRelationNameTestCase,
)

_LONG_BASE: str = "orders_by_region_" * 80
_HASHES: dict[int, str] = {
    length: hashlib.sha256(_LONG_BASE[:length].encode("utf-8")).hexdigest()[:8]
    for length in (55, 60, 63, 128, 255, 1024)
}
_MULTIBYTE_BASE: str = "a" * 44 + "ü" * 10
_MULTIBYTE_HASH: str = hashlib.sha256(_MULTIBYTE_BASE.encode("utf-8")).hexdigest()[:8]
_SIBLING_HASH: str = hashlib.sha256(f"{_LONG_BASE[:62]}x".encode()).hexdigest()[:8]


@pytest.mark.parametrize(
    "test_case",
    [
        FitAuxiliaryRelationNameTestCase(
            description="name that fits keeps the plain suffix",
            base_name=_LONG_BASE[:54],
            suffix="__staging",
            identifier_limit=63,
            expected_name=f"{_LONG_BASE[:54]}__staging",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="one character over the 63 limit is hashed",
            base_name=_LONG_BASE[:55],
            suffix="__staging",
            identifier_limit=63,
            expected_name=f"{_LONG_BASE[:45]}_{_HASHES[55]}__staging",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="target at the 63 limit (DuckDB, MotherDuck, Postgres)",
            base_name=_LONG_BASE[:63],
            suffix="__staging",
            identifier_limit=63,
            expected_name=f"{_LONG_BASE[:45]}_{_HASHES[63]}__staging",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="sibling target sharing the prefix gets a different name",
            base_name=f"{_LONG_BASE[:62]}x",
            suffix="__staging",
            identifier_limit=63,
            expected_name=f"{_LONG_BASE[:45]}_{_SIBLING_HASH}__staging",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="type enforcement suffix on a long staging name",
            base_name=_LONG_BASE[:60],
            suffix="__enforced",
            identifier_limit=63,
            expected_name=f"{_LONG_BASE[:44]}_{_HASHES[60]}__enforced",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="target at the 128 limit (SQL Server)",
            base_name=_LONG_BASE[:128],
            suffix="__delta",
            identifier_limit=128,
            expected_name=f"{_LONG_BASE[:112]}_{_HASHES[128]}__delta",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="target at the 255 limit (Snowflake, Databricks)",
            base_name=_LONG_BASE[:255],
            suffix="__snapshot_delta",
            identifier_limit=255,
            expected_name=f"{_LONG_BASE[:230]}_{_HASHES[255]}__snapshot_delta",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="target at the 1024 limit (BigQuery)",
            base_name=_LONG_BASE[:1024],
            suffix="__staging",
            identifier_limit=1024,
            expected_name=f"{_LONG_BASE[:1006]}_{_HASHES[1024]}__staging",
        ),
        FitAuxiliaryRelationNameTestCase(
            description="name fitting by characters but not bytes is cut on a character boundary",
            base_name=_MULTIBYTE_BASE,
            suffix="__staging",
            identifier_limit=63,
            expected_name=f"{'a' * 44}_{_MULTIBYTE_HASH}__staging",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_identifier_limit_when_fitting_auxiliary_name_then_returns_expected_name(
    test_case: FitAuxiliaryRelationNameTestCase,
) -> None:
    fitted: str = fit_auxiliary_relation_name(
        base_name=test_case.base_name,
        suffix=test_case.suffix,
        identifier_limit=test_case.identifier_limit,
    )

    assert fitted == test_case.expected_name
    assert len(fitted.encode("utf-8")) <= test_case.identifier_limit
    assert fitted != test_case.base_name


@pytest.mark.parametrize(
    "test_case",
    [
        FitAuxiliaryRelationNameErrorTestCase(
            description="suffix longer than the limit is rejected",
            base_name="orders",
            suffix="_" * 70,
            identifier_limit=63,
            expected_error_fragment="cannot fit within identifier limit 63",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_oversized_suffix_when_fitting_auxiliary_name_then_raises(
    test_case: FitAuxiliaryRelationNameErrorTestCase,
) -> None:
    with pytest.raises(SharedInputError, match=test_case.expected_error_fragment):
        _ = fit_auxiliary_relation_name(
            base_name=test_case.base_name,
            suffix=test_case.suffix,
            identifier_limit=test_case.identifier_limit,
        )
