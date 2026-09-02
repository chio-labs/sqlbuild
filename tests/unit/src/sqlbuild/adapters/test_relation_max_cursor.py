from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    AdapterEligibleMaxCursorSqlTestCase,
    AdapterRelationMaxCursorTestCase,
    AdapterSeedSelectAfterCursorTestCase,
)
from tests.unit.src.sqlbuild.adapters.helpers import (
    AdapterCursorRecordingConnection,
    AdapterExecuteRecordingConnection,
    adapter_closed_cursor_count,
    adapter_cursor_executed_sql,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterRelationMaxCursorTestCase(
            description="duckdb uses shared quoted cursor SQL",
            adapter=DuckDbAdapter(),
            connection=AdapterExecuteRecordingConnection(rows=((9,),)),
            relation="analytics.events",
            cursor_column='event"time',
            expected_value=9,
            expected_sql=('SELECT max("event""time") FROM analytics.events',),
            expected_closed_cursor_count=0,
        ),
        AdapterRelationMaxCursorTestCase(
            description="motherduck uses shared quoted cursor SQL",
            adapter=MotherDuckAdapter(),
            connection=AdapterExecuteRecordingConnection(rows=((10,),)),
            relation="analytics.events",
            cursor_column='event"time',
            expected_value=10,
            expected_sql=('SELECT max("event""time") FROM analytics.events',),
            expected_closed_cursor_count=0,
        ),
        AdapterRelationMaxCursorTestCase(
            description="postgres uses double quoted cursor SQL",
            adapter=PostgresAdapter(),
            connection=AdapterExecuteRecordingConnection(rows=((11,),)),
            relation="analytics.events",
            cursor_column='event"time',
            expected_value=11,
            expected_sql=('SELECT max("event""time") FROM analytics.events',),
            expected_closed_cursor_count=0,
        ),
        AdapterRelationMaxCursorTestCase(
            description="bigquery uses backtick quoted cursor SQL",
            adapter=BigQueryAdapter(),
            connection=AdapterExecuteRecordingConnection(rows=((12,),)),
            relation="analytics.events",
            cursor_column="event`time",
            expected_value=12,
            expected_sql=("SELECT max(`event``time`) FROM analytics.events",),
            expected_closed_cursor_count=0,
        ),
        AdapterRelationMaxCursorTestCase(
            description="sqlserver uses bracket quoted cursor SQL",
            adapter=SqlServerAdapter(),
            connection=AdapterExecuteRecordingConnection(rows=((13,),)),
            relation="analytics.events",
            cursor_column="event]time",
            expected_value=13,
            expected_sql=("SELECT max([event]]time]) FROM analytics.events",),
            expected_closed_cursor_count=0,
        ),
        AdapterRelationMaxCursorTestCase(
            description="snowflake uppercases and closes cursor",
            adapter=SnowflakeAdapter(),
            connection=AdapterCursorRecordingConnection(rows=((14,),)),
            relation="analytics.events",
            cursor_column='event"time',
            expected_value=14,
            expected_sql=('SELECT max("EVENT""TIME") FROM analytics.events',),
            expected_closed_cursor_count=1,
        ),
        AdapterRelationMaxCursorTestCase(
            description="databricks uses backtick cursor SQL and closes cursor",
            adapter=DatabricksAdapter(),
            connection=AdapterCursorRecordingConnection(rows=((15,),)),
            relation="analytics.events",
            cursor_column="event`time",
            expected_value=15,
            expected_sql=("SELECT max(`event``time`) FROM analytics.events",),
            expected_closed_cursor_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_first_class_adapter_when_getting_relation_max_cursor_then_uses_adapter_sql(
    test_case: AdapterRelationMaxCursorTestCase,
) -> None:
    result: object | None = test_case.adapter.get_relation_max_cursor(
        connection=test_case.connection,
        relation=test_case.relation,
        cursor_column=test_case.cursor_column,
    )

    assert result == test_case.expected_value
    assert adapter_cursor_executed_sql(test_case.connection) == test_case.expected_sql
    assert (
        adapter_closed_cursor_count(test_case.connection) == test_case.expected_closed_cursor_count
    )


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterEligibleMaxCursorSqlTestCase(
            "duckdb date predicate",
            DuckDbAdapter(),
            'event"time',
            "2026-09-01",
            True,
            'SELECT MAX("event""time") FROM analytics.events '
            'WHERE "event""time" <= CAST(\'2026-09-01\' AS DATE)',
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "motherduck date predicate",
            MotherDuckAdapter(),
            'event"time',
            "2026-09-01",
            True,
            'SELECT MAX("event""time") FROM analytics.events '
            'WHERE "event""time" <= CAST(\'2026-09-01\' AS DATE)',
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "postgres date predicate",
            PostgresAdapter(),
            'event"time',
            "2026-09-01",
            True,
            'SELECT MAX("event""time") FROM analytics.events '
            'WHERE "event""time" <= CAST(\'2026-09-01\' AS DATE)',
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "bigquery date predicate",
            BigQueryAdapter(),
            "event`time",
            "2026-09-01",
            True,
            "SELECT MAX(`event``time`) FROM analytics.events "
            "WHERE `event``time` <= CAST('2026-09-01' AS DATE)",
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "sqlserver date predicate",
            SqlServerAdapter(),
            "event]time",
            "2026-09-01",
            True,
            "SELECT MAX([event]]time]) FROM analytics.events "
            "WHERE [event]]time] <= CAST('2026-09-01' AS DATE)",
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "snowflake date predicate",
            SnowflakeAdapter(),
            'event"time',
            "2026-09-01",
            True,
            'SELECT MAX("EVENT""TIME") FROM analytics.events '
            'WHERE "EVENT""TIME" <= CAST(\'2026-09-01\' AS DATE)',
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "databricks date predicate",
            DatabricksAdapter(),
            "event`time",
            "2026-09-01",
            True,
            "SELECT MAX(`event``time`) FROM analytics.events "
            "WHERE `event``time` <= CAST('2026-09-01' AS DATE)",
        ),
        AdapterEligibleMaxCursorSqlTestCase(
            "sqlserver timestamp predicate",
            SqlServerAdapter(),
            "event]time",
            "2026-09-01T12:00:00",
            False,
            "SELECT MAX([event]]time]) FROM analytics.events WHERE [event]]time] <= "
            "CAST('2026-09-01T12:00:00' AS DATETIME2(6))",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cursor_horizon_when_rendering_eligible_max_then_adapter_owns_portable_sql(
    test_case: AdapterEligibleMaxCursorSqlTestCase,
) -> None:
    sql: str = test_case.adapter.render_max_cursor_at_or_before(
        relation="analytics.events",
        cursor_column=test_case.cursor_column,
        maximum_allowed=test_case.maximum_allowed,
        cursor_type="timestamp",
        is_date=test_case.is_date,
    )

    assert sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterSeedSelectAfterCursorTestCase(
            description="duckdb renders seed select after timestamp cursor",
            adapter=DuckDbAdapter(),
            origin="prod.events",
            cursor_column='event"time',
            cursor_start_exclusive="2026-01-01 00:00:00",
            cursor_type="timestamp",
            expected_sql=(
                'SELECT * FROM prod.events WHERE "event""time" > TIMESTAMP \'2026-01-01 00:00:00\''
            ),
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="motherduck renders seed select after timestamp cursor",
            adapter=MotherDuckAdapter(),
            origin="prod.events",
            cursor_column='event"time',
            cursor_start_exclusive="2026-01-01 00:00:00",
            cursor_type="timestamp",
            expected_sql=(
                'SELECT * FROM prod.events WHERE "event""time" > TIMESTAMP \'2026-01-01 00:00:00\''
            ),
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="postgres renders seed select after integer cursor",
            adapter=PostgresAdapter(),
            origin="prod.events",
            cursor_column='event"index',
            cursor_start_exclusive="10",
            cursor_type="integer",
            expected_sql='SELECT * FROM prod.events WHERE "event""index" > 10',
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="bigquery renders seed select with backtick cursor",
            adapter=BigQueryAdapter(),
            origin="prod.events",
            cursor_column="event`time",
            cursor_start_exclusive="2026-01-01 00:00:00",
            cursor_type="timestamp",
            expected_sql=(
                "SELECT * FROM prod.events WHERE `event``time` > TIMESTAMP '2026-01-01 00:00:00'"
            ),
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="sqlserver renders seed select with bracket cursor",
            adapter=SqlServerAdapter(),
            origin="prod.events",
            cursor_column="event]index",
            cursor_start_exclusive="10",
            cursor_type="integer",
            expected_sql="SELECT * FROM prod.events WHERE [event]]index] > 10",
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="snowflake renders seed select with uppercase quoted cursor",
            adapter=SnowflakeAdapter(),
            origin="prod.events",
            cursor_column='event"time',
            cursor_start_exclusive="2026-01-01 00:00:00",
            cursor_type="timestamp",
            expected_sql=(
                'SELECT * FROM prod.events WHERE "EVENT""TIME" > TIMESTAMP \'2026-01-01 00:00:00\''
            ),
        ),
        AdapterSeedSelectAfterCursorTestCase(
            description="databricks renders seed select with backtick cursor",
            adapter=DatabricksAdapter(),
            origin="prod.events",
            cursor_column="event`time",
            cursor_start_exclusive="2026-01-01 00:00:00",
            cursor_type="timestamp",
            expected_sql=(
                "SELECT * FROM prod.events WHERE `event``time` > TIMESTAMP '2026-01-01 00:00:00'"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_first_class_adapter_when_rendering_seed_select_after_cursor_then_uses_adapter_sql(
    test_case: AdapterSeedSelectAfterCursorTestCase,
) -> None:
    sql: str = test_case.adapter.render_seed_select_after_cursor(
        origin=test_case.origin,
        cursor_column=test_case.cursor_column,
        cursor_start_exclusive=test_case.cursor_start_exclusive,
        cursor_type=test_case.cursor_type,
    )

    assert sql == test_case.expected_sql
