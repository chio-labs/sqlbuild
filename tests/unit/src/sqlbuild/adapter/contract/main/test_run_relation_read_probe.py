from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationReadProbe
from sqlbuild.adapter.contract.types import RelationReadStatus
from tests.unit.src.sqlbuild.adapter.contract.main._test_types import (
    RelationProbeClassificationTestCase,
)
from tests.unit.src.sqlbuild.adapter.contract.main.helpers import (
    ADAPTERS_BY_NAME,
    BinderException,
    CatalogException,
    Forbidden,
    NotFound,
    ProgrammingError,
    RecordingProbeConnection,
    UndefinedTable,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationProbeClassificationTestCase(
            description="snowflake readable relation exists",
            adapter_name="snowflake",
            errors=(),
            expected_status=RelationReadStatus.READABLE,
        ),
        RelationProbeClassificationTestCase(
            description="snowflake 002003 does not exist or not authorized is missing",
            adapter_name="snowflake",
            errors=(
                ProgrammingError(
                    "002003 (42S02): Object 'RAW.ORDERS' does not exist or not authorized.",
                    errno=2003,
                ),
            ),
            expected_status=RelationReadStatus.MISSING_OR_UNREADABLE,
        ),
        RelationProbeClassificationTestCase(
            description="snowflake 2043 object does not exist is missing",
            adapter_name="snowflake",
            errors=(ProgrammingError("Object does not exist", errno=2043),),
            expected_status=RelationReadStatus.MISSING_OR_UNREADABLE,
        ),
        RelationProbeClassificationTestCase(
            description="postgres 42P01 undefined table is missing",
            adapter_name="postgres",
            errors=(UndefinedTable('relation "raw.orders" does not exist', sqlstate="42P01"),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="sql server 208 invalid object name is missing",
            adapter_name="sqlserver",
            errors=(Exception(208, b"Invalid object name 'raw.orders'."),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="databricks table or view not found is missing",
            adapter_name="databricks",
            errors=(Exception("[TABLE_OR_VIEW_NOT_FOUND] The table or view `raw`.`orders`"),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="bigquery not found is missing through the adapter error wrapper",
            adapter_name="bigquery",
            errors=(NotFound("Not found: Table example-project:raw.orders"),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="databricks schema not found is missing",
            adapter_name="databricks",
            errors=(Exception("[SCHEMA_NOT_FOUND] The schema `raw` cannot be found."),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="databricks catalog not found is missing",
            adapter_name="databricks",
            errors=(Exception("[CATALOG_NOT_FOUND] The catalog `lake` cannot be found."),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="duckdb missing attached catalog is missing",
            adapter_name="duckdb",
            errors=(BinderException('Binder Error: Catalog "lake" does not exist!'),),
            expected_status=RelationReadStatus.MISSING,
        ),
        RelationProbeClassificationTestCase(
            description="duckdb catalog does not exist is missing",
            adapter_name="duckdb",
            errors=(CatalogException("Catalog Error: Table with name orders does not exist!"),),
            expected_status=RelationReadStatus.MISSING,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_probe_outcome_when_checking_relation_then_classifies_not_found(
    test_case: RelationProbeClassificationTestCase,
) -> None:
    adapter: BaseAdapter = ADAPTERS_BY_NAME[test_case.adapter_name]()
    connection: RecordingProbeConnection = RecordingProbeConnection(
        errors=test_case.errors, role=test_case.role
    )

    probe: RelationReadProbe = adapter.probe_relation_read(
        connection=connection, relation="raw.orders"
    )

    assert probe.status == test_case.expected_status
    assert probe.role == test_case.expected_role
    assert connection.statements[0] == "SELECT 1 FROM raw.orders WHERE 1=0"


@pytest.mark.parametrize(
    "test_case",
    [
        RelationProbeClassificationTestCase(
            description="snowflake session error is re-raised",
            adapter_name="snowflake",
            errors=(ProgrammingError("Authentication token has expired", errno=390114),),
            expected_status=None,
        ),
        RelationProbeClassificationTestCase(
            description="postgres permission error is re-raised",
            adapter_name="postgres",
            errors=(UndefinedTable("permission denied for table orders", sqlstate="42501"),),
            expected_status=None,
        ),
        RelationProbeClassificationTestCase(
            description="sql server permission error is re-raised",
            adapter_name="sqlserver",
            errors=(Exception(229, b"The SELECT permission was denied"),),
            expected_status=None,
        ),
        RelationProbeClassificationTestCase(
            description="databricks permission error is re-raised",
            adapter_name="databricks",
            errors=(Exception("[INSUFFICIENT_PERMISSIONS] User does not have SELECT"),),
            expected_status=None,
        ),
        RelationProbeClassificationTestCase(
            description="bigquery forbidden is re-raised",
            adapter_name="bigquery",
            errors=(Forbidden("Access Denied: Table example-project:raw.orders"),),
            expected_status=None,
        ),
        RelationProbeClassificationTestCase(
            description="duckdb io error is re-raised",
            adapter_name="duckdb",
            errors=(OSError("IO Error: could not read file"),),
            expected_status=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_other_probe_error_when_checking_relation_then_reraises(
    test_case: RelationProbeClassificationTestCase,
) -> None:
    adapter: BaseAdapter = ADAPTERS_BY_NAME[test_case.adapter_name]()
    connection: RecordingProbeConnection = RecordingProbeConnection(errors=test_case.errors)

    with pytest.raises(Exception) as raised:
        adapter.probe_relation_read(connection=connection, relation="raw.orders")

    assert test_case.expected_status is None
    assert str(test_case.errors[0]) in str(raised.value)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
