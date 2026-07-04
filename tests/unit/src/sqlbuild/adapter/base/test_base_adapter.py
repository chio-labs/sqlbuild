from __future__ import annotations

from typing import ClassVar

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models.core import FunctionArgument
from sqlbuild.compiler.compile.types import FunctionLanguage
from tests.unit.src.sqlbuild.adapter.base._test_types import (
    BaseAdapterDurableCloneTestCase,
    BaseAdapterExpressionInferenceProfileTestCase,
    BaseAdapterIdentifierLimitTestCase,
    BaseAdapterMetadataSqlTestCase,
    BaseAdapterPythonFunctionSupportTestCase,
    BaseAdapterRelationMaxCursorTestCase,
    BaseAdapterSqlAnalysisDialectTestCase,
)
from tests.unit.src.sqlbuild.adapter.base.helpers import (
    RecordingBaseAdapter,
    RecordingConnection,
)


class ConcreteBaseAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        del connection


class PostgresLikeBaseAdapter(ConcreteBaseAdapter):
    sql_analysis_dialect_name: ClassVar[str | None] = "postgres"


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterPythonFunctionSupportTestCase(
            description="raises clear error for Python UDFs by default",
            expected_error_fragment="does not support Python UDFs",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_function_when_rendering_with_base_adapter_then_raises_clear_error(
    test_case: BaseAdapterPythonFunctionSupportTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    with pytest.raises(AdapterUserError) as exc_info:
        adapter.render_create_function(
            destination="main.is_positive_int",
            arguments=(FunctionArgument(name="a_string", type="VARCHAR"),),
            returns="BOOLEAN",
            body_sql="def main(a_string): return True",
            language=FunctionLanguage.PYTHON,
            runtime_version="3.11",
            entry_point="main",
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterExpressionInferenceProfileTestCase(
            description="returns portable inference profile by default",
            expected_sql_analysis_dialect=None,
            expected_function_rules_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_base_adapter_when_getting_inference_profile_then_returns_portable_defaults(
    test_case: BaseAdapterExpressionInferenceProfileTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    assert len(profile.function_nullability_rules) == test_case.expected_function_rules_count


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterSqlAnalysisDialectTestCase(
            description="returns none by default",
            expected_sql_analysis_dialect=None,
        ),
        BaseAdapterSqlAnalysisDialectTestCase(
            description="returns class configured dialect",
            expected_sql_analysis_dialect="postgres",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_base_adapter_subclass_when_getting_sql_analysis_dialect_then_uses_class_setting(
    test_case: BaseAdapterSqlAnalysisDialectTestCase,
) -> None:
    adapter: BaseAdapter = (
        PostgresLikeBaseAdapter()
        if test_case.expected_sql_analysis_dialect is not None
        else ConcreteBaseAdapter()
    )

    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect
    assert adapter.expression_inference_profile().sql_analysis_dialect == (
        test_case.expected_sql_analysis_dialect
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterIdentifierLimitTestCase(
            description="returns postgres-compatible identifier limit by default",
            expected_identifier_limit=63,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_base_adapter_when_getting_identifier_limit_then_returns_portable_default(
    test_case: BaseAdapterIdentifierLimitTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterDurableCloneTestCase(
            description="renders durable clone as CTAS fallback by default",
            source="prod.fact_orders",
            target="dev.fact_orders",
            expected_supports_durable_clone=False,
            expected_statements=(
                "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_base_adapter_when_rendering_durable_clone_then_uses_copy_fallback(
    test_case: BaseAdapterDurableCloneTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    result: tuple[str, ...] = adapter.render_durable_clone(
        origin=test_case.source,
        destination=test_case.target,
    )

    assert adapter.supports_durable_clone() is test_case.expected_supports_durable_clone
    assert result == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    (
        BaseAdapterRelationMaxCursorTestCase(
            description="queries max cursor with quoted identifier",
            rows=((42,),),
            relation="analytics.events",
            cursor_column='event"time',
            expected_value=42,
            expected_sql='SELECT max("event""time") FROM analytics.events',
        ),
        BaseAdapterRelationMaxCursorTestCase(
            description="returns none when query returns no rows",
            rows=(),
            relation="analytics.empty_events",
            cursor_column="event_time",
            expected_value=None,
            expected_sql='SELECT max("event_time") FROM analytics.empty_events',
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relation_when_getting_max_cursor_then_base_adapter_queries_quoted_cursor(
    test_case: BaseAdapterRelationMaxCursorTestCase,
) -> None:
    adapter: RecordingBaseAdapter = RecordingBaseAdapter()
    connection: RecordingConnection = RecordingConnection(rows=test_case.rows)

    result: object | None = adapter.get_relation_max_cursor(
        connection,
        relation=test_case.relation,
        cursor_column=test_case.cursor_column,
    )

    assert result == test_case.expected_value
    assert tuple(connection.executed_sql) == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterMetadataSqlTestCase(
            description="escapes single quotes in metadata SQL literals",
            database="warehouse'prod",
            schema="sales'ops",
            name="orders'2026",
            expected_sql=(
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = 'sales''ops' AND catalog_name = 'warehouse''prod'",
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'orders''2026' "
                "AND table_schema = 'sales''ops' AND table_catalog = 'warehouse''prod'",
                "SELECT table_name, table_schema, table_type "
                "FROM information_schema.tables WHERE 1=1 "
                "AND table_schema IN ('sales''ops') "
                "AND table_name IN ('orders''2026') AND table_catalog = 'warehouse''prod'",
                "SELECT routine_name, routine_schema, routine_type "
                "FROM information_schema.routines WHERE 1=1 "
                "AND routine_schema IN ('sales''ops') "
                "AND routine_name IN ('orders''2026') AND routine_catalog = 'warehouse''prod'",
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'orders''2026' "
                "AND table_schema = 'sales''ops' AND table_catalog = 'warehouse''prod' "
                "ORDER BY ordinal_position",
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns WHERE 1=1 "
                "AND table_schema IN ('sales''ops') "
                "AND table_name IN ('orders''2026') AND table_catalog = 'warehouse''prod' "
                "ORDER BY table_name, ordinal_position",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_names_with_quotes_when_querying_then_base_adapter_escapes_literals(
    test_case: BaseAdapterMetadataSqlTestCase,
) -> None:
    adapter: RecordingBaseAdapter = RecordingBaseAdapter()
    connection: RecordingConnection = RecordingConnection()

    adapter.schema_exists(connection, database=test_case.database, schema=test_case.schema)
    adapter.relation_exists(
        connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    adapter.list_relations(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )
    adapter.list_functions(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )
    adapter.get_columns(
        connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    adapter.get_all_columns(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )

    assert tuple(connection.executed_sql) == test_case.expected_sql
