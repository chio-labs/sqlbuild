"""Review schema names survive the identifier folding of the warehouses a review runs on."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from sqlbuild._native import parse_review_schema_name
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.review.main.create_review_schema import create_review_schema
from sqlbuild.executor.review.main.drop_review_schema import drop_review_schema
from tests.unit.src.sqlbuild.executor.review.main._test_types import ReviewSchemaFoldingTestCase
from tests.unit.src.sqlbuild.executor.review.main.helpers import FoldingWarehouseAdapter

REVIEW_SCHEMA: str = "review_20261023t101500z_3f2a9c1_a1b2c3"
CREATED_AT: datetime = datetime(2026, 10, 23, 10, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    (
        ReviewSchemaFoldingTestCase(
            description="postgres-style lowercase folding with an exact comparison",
            fold=str.lower,
            compare=str,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
        ReviewSchemaFoldingTestCase(
            description="snowflake-style uppercase folding with a case-insensitive comparison",
            fold=str.upper,
            compare=str.upper,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_folded_review_schema_when_dropping_then_it_is_found_and_gone(
    test_case: ReviewSchemaFoldingTestCase,
) -> None:
    adapter: FoldingWarehouseAdapter = FoldingWarehouseAdapter(
        fold=test_case.fold, compare=test_case.compare, schemas=(REVIEW_SCHEMA,)
    )

    dropped: bool = drop_review_schema(
        adapter=cast(Any, adapter), connection=None, database=None, schema=REVIEW_SCHEMA
    )

    assert dropped is test_case.expected_dropped
    assert adapter.schemas == set()


@pytest.mark.parametrize(
    "test_case",
    (
        ReviewSchemaFoldingTestCase(
            description="postgres-style lowercase folding with an exact comparison",
            fold=str.lower,
            compare=str,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
        ReviewSchemaFoldingTestCase(
            description="snowflake-style uppercase folding with a case-insensitive comparison",
            fold=str.upper,
            compare=str.upper,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_existing_folded_review_schema_when_creating_then_it_is_refused(
    test_case: ReviewSchemaFoldingTestCase,
) -> None:
    adapter: FoldingWarehouseAdapter = FoldingWarehouseAdapter(
        fold=test_case.fold, compare=test_case.compare, schemas=(REVIEW_SCHEMA,)
    )

    with pytest.raises(ExecutorInputError) as raised:
        create_review_schema(
            adapter=cast(Any, adapter),
            connection=None,
            database=None,
            schema=REVIEW_SCHEMA,
            marker_database=None,
            marker_schema="dev",
            run_id="a1b2c3",
            created_at=CREATED_AT,
        )

    assert raised.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    (
        ReviewSchemaFoldingTestCase(
            description="postgres-style lowercase folding with an exact comparison",
            fold=str.lower,
            compare=str,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
        ReviewSchemaFoldingTestCase(
            description="snowflake-style uppercase folding with a case-insensitive comparison",
            fold=str.upper,
            compare=str.upper,
            expected_dropped=True,
            expected_code="C765",
            expected_created_at=CREATED_AT,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_folded_review_schema_name_when_parsing_then_creation_time_is_read(
    test_case: ReviewSchemaFoldingTestCase,
) -> None:
    parsed: datetime | None = parse_review_schema_name(test_case.fold(REVIEW_SCHEMA))

    assert parsed is not None
    assert parsed.astimezone(UTC) == test_case.expected_created_at


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
