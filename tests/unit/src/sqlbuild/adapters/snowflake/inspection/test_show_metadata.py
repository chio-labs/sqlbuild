"""SHOW TABLES and SHOW VIEWS rows map onto INFORMATION_SCHEMA.TABLES relation semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from sqlbuild.adapter.relations.models import ListedRelation
from sqlbuild.adapters.snowflake._helpers.show_metadata import (
    is_missing_object_error,
    listed_relation_from_show_table,
    listed_relation_from_show_view,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection._test_types import (
    MissingObjectErrorTestCase,
    ShowRelationRowTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    FakeSnowflakeProgrammingError,
    show_relation_row,
)

_CREATED_ON: datetime = datetime(2026, 3, 1, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        ShowRelationRowTestCase(
            description="permanent table",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON, kind="TABLE", retention_time="1", is_external="N"
            ),
            expected_relation_type="base table",
            expected_is_transient=False,
            expected_retention_days=1,
        ),
        ShowRelationRowTestCase(
            description="transient table",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON, kind="TRANSIENT", retention_time="0", is_external="N"
            ),
            expected_relation_type="base table",
            expected_is_transient=True,
            expected_retention_days=0,
        ),
        ShowRelationRowTestCase(
            description="dynamic table is a base table",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON,
                kind="TABLE",
                retention_time="1",
                is_external="N",
                is_dynamic="Y",
            ),
            expected_relation_type="base table",
            expected_is_transient=False,
            expected_retention_days=1,
        ),
        ShowRelationRowTestCase(
            description="temporary table",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON, kind="TEMPORARY", retention_time="1", is_external="N"
            ),
            expected_relation_type="temporary table",
            expected_is_transient=False,
            expected_retention_days=1,
        ),
        ShowRelationRowTestCase(
            description="external table without retention",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON, kind="TABLE", retention_time="", is_external="Y"
            ),
            expected_relation_type="external table",
            expected_is_transient=False,
            expected_retention_days=None,
        ),
        ShowRelationRowTestCase(
            description="event table",
            is_view=False,
            row=show_relation_row(
                created_on=_CREATED_ON,
                kind="TABLE",
                retention_time="1",
                is_external="N",
                is_event="Y",
            ),
            expected_relation_type="event table",
            expected_is_transient=False,
            expected_retention_days=1,
        ),
        ShowRelationRowTestCase(
            description="older output without flag columns",
            is_view=False,
            row=show_relation_row(created_on=_CREATED_ON, kind="TABLE", retention_time=None),
            expected_relation_type="base table",
            expected_is_transient=False,
            expected_retention_days=None,
        ),
        ShowRelationRowTestCase(
            description="view",
            is_view=True,
            row=show_relation_row(
                created_on=_CREATED_ON, is_materialized="false", is_secure="false"
            ),
            expected_relation_type="view",
            expected_is_transient=False,
            expected_retention_days=None,
        ),
        ShowRelationRowTestCase(
            description="materialized view as text flag",
            is_view=True,
            row=show_relation_row(created_on=_CREATED_ON, is_materialized="true"),
            expected_relation_type="materialized view",
            expected_is_transient=False,
            expected_retention_days=None,
        ),
        ShowRelationRowTestCase(
            description="materialized view as boolean flag",
            is_view=True,
            row=show_relation_row(created_on=_CREATED_ON, is_materialized=True),
            expected_relation_type="materialized view",
            expected_is_transient=False,
            expected_retention_days=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_show_row_when_mapping_then_matches_information_schema_relation(
    test_case: ShowRelationRowTestCase,
) -> None:
    mappers: tuple[Callable[..., ListedRelation], ...] = (
        listed_relation_from_show_table,
        listed_relation_from_show_view,
    )

    listed: ListedRelation = mappers[test_case.is_view](row=test_case.row, database="analytics")

    assert listed.stored_name == "ORDERS"
    assert (listed.relation.database, listed.relation.schema, listed.relation.name) == (
        "analytics",
        "staging",
        "orders",
    )
    assert listed.relation.relation_type == test_case.expected_relation_type
    assert listed.relation.is_transient is test_case.expected_is_transient
    assert listed.relation.retention_days == test_case.expected_retention_days
    assert listed.relation.created_at == _CREATED_ON
    assert listed.relation.last_altered_at is None


@pytest.mark.parametrize(
    "test_case",
    [
        MissingObjectErrorTestCase(
            description="driver error number",
            errno=2003,
            message="SQL compilation error",
            expected_missing=True,
        ),
        MissingObjectErrorTestCase(
            description="message without error number",
            errno=None,
            message="Schema 'ANALYTICS.STAGING' does not exist or not authorized.",
            expected_missing=True,
        ),
        MissingObjectErrorTestCase(
            description="other failure",
            errno=390,
            message="Metadata service unavailable",
            expected_missing=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_show_failure_when_classifying_then_only_missing_schemas_list_nothing(
    test_case: MissingObjectErrorTestCase,
) -> None:
    error: Exception = (
        RuntimeError(test_case.message),
        FakeSnowflakeProgrammingError(test_case.message, errno=test_case.errno or 0),
    )[test_case.errno is not None]

    assert is_missing_object_error(error) is test_case.expected_missing


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
