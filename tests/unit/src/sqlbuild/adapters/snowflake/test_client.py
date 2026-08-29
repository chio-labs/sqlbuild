from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    RelationInfo,
    SchemaDiffResult,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.adapter.contract.types import CursorKind, FunctionNullabilityRule
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.compile.models import (
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeConnectConfigTestCase,
    SnowflakeExpressionInferenceProfileTestCase,
    SnowflakeInformationSchemaFilterTestCase,
    SnowflakeInvalidSecondaryRolesTestCase,
    SnowflakeLoadSeedTestCase,
    SnowflakeMergeExclusionTestCase,
    SnowflakeMoveOrCopyRelationTestCase,
    SnowflakePruneSqlTestCase,
    SnowflakeQualifiedColumnInspectionTestCase,
    SnowflakeQueryColumnNamesTestCase,
    SnowflakeRenderCloneTestCase,
    SnowflakeRenderCursorBoundLiteralTestCase,
    SnowflakeRenderIdentifierTestCase,
    SnowflakeRenderPythonFunctionTestCase,
    SnowflakeRenderTableFunctionTestCase,
    SnowflakeSchemaDiffTestCase,
    SnowflakeTableFreshnessBatchTestCase,
    SnowflakeTableFreshnessMetadataErrorTestCase,
    SnowflakeTableFreshnessMetadataTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeDescribeConnection,
    FakeSnowflakeDescribeCursor,
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
    FakeSnowflakeMetadataSequenceConnection,
    FakeSnowflakeRawConnection,
    build_bulk_columns_rows,
    build_bulk_sequence_connection,
    build_qualified_column_relations,
    build_show_columns_rows,
    describe_equivalent_numeric_relation,
    expected_qualified_columns,
    install_fake_snowflake_connector,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeExpressionInferenceProfileTestCase(
            description="returns Snowflake inference rules",
            expected_sql_analysis_dialect="snowflake",
            expected_identifier_limit=255,
            expected_rule_results={
                "IFF": InferredNullability.NON_NULL,
                "UPPER": InferredNullability.NON_NULL,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_adapter_when_getting_inference_profile_then_returns_expected_rules(
    test_case: SnowflakeExpressionInferenceProfileTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit
    iff_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("IFF")
    upper_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("UPPER")
    assert iff_rule is not None
    assert upper_rule is not None
    assert (
        iff_rule(
            (
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            )
        )
        == test_case.expected_rule_results["IFF"]
    )
    assert upper_rule((InferredNullability.NON_NULL,)) == test_case.expected_rule_results["UPPER"]


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectConfigTestCase(
            description="defaults MFA token cache flags for username password MFA",
            config={
                "account": "acct",
                "user": "analytics",
                "password": "secret",
                "authenticator": "username_password_mfa",
            },
            expected_connect_kwargs={
                "account": "acct",
                "user": "analytics",
                "password": "secret",
                "authenticator": "username_password_mfa",
                "client_request_mfa_token": True,
                "client_store_temporary_credential": True,
            },
        ),
        SnowflakeConnectConfigTestCase(
            description="preserves explicit MFA token cache flags",
            config={
                "account": "acct",
                "authenticator": "username_password_mfa",
                "client_request_mfa_token": False,
                "client_store_temporary_credential": False,
            },
            expected_connect_kwargs={
                "account": "acct",
                "authenticator": "username_password_mfa",
                "client_request_mfa_token": False,
                "client_store_temporary_credential": False,
            },
        ),
        SnowflakeConnectConfigTestCase(
            description="defaults OAuth authorization code token caching",
            config={
                "account": "acct",
                "user": "analytics",
                "authenticator": "OAUTH_AUTHORIZATION_CODE",
            },
            expected_connect_kwargs={
                "account": "acct",
                "user": "analytics",
                "authenticator": "OAUTH_AUTHORIZATION_CODE",
                "client_store_temporary_credential": True,
                "oauth_enable_refresh_tokens": True,
            },
        ),
        SnowflakeConnectConfigTestCase(
            description="preserves explicit OAuth authorization code cache flags",
            config={
                "account": "acct",
                "authenticator": "OAUTH_AUTHORIZATION_CODE",
                "client_store_temporary_credential": False,
                "oauth_enable_refresh_tokens": False,
            },
            expected_connect_kwargs={
                "account": "acct",
                "authenticator": "OAUTH_AUTHORIZATION_CODE",
                "client_store_temporary_credential": False,
                "oauth_enable_refresh_tokens": False,
            },
        ),
        SnowflakeConnectConfigTestCase(
            description="strips SQLBuild routing keys before connector call",
            config={
                "source": "explicit",
                "profile": "analytics",
                "target": "dev",
                "project_dir": "dbt_project",
                "profiles_dir": "profiles",
                "account": "acct",
                "authenticator": "programmatic_access_token",
                "token": "secret-token",
            },
            expected_connect_kwargs={
                "account": "acct",
                "authenticator": "programmatic_access_token",
                "token": "secret-token",
            },
        ),
        SnowflakeConnectConfigTestCase(
            description="allows explicit secondary roles",
            config={
                "account": "acct",
                "authenticator": "programmatic_access_token",
                "token": "secret-token",
                "secondary_roles": "ALL",
            },
            expected_connect_kwargs={
                "account": "acct",
                "authenticator": "programmatic_access_token",
                "token": "secret-token",
            },
            expected_session_statements=("USE SECONDARY ROLES ALL",),
        ),
        SnowflakeConnectConfigTestCase(
            description="disables secondary roles before selecting primary session context",
            config={
                "account": "acct",
                "role": "DEVELOPER",
                "warehouse": "DEV_WH",
                "database": "ANALYTICS",
            },
            expected_connect_kwargs={
                "account": "acct",
                "role": "DEVELOPER",
                "warehouse": "DEV_WH",
                "database": "ANALYTICS",
            },
            expected_session_statements=(
                "USE SECONDARY ROLES NONE",
                "USE ROLE DEVELOPER",
                "USE WAREHOUSE DEV_WH",
                "USE DATABASE ANALYTICS",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_connection_config_when_connecting_then_uses_expected_connector_and_session_config(
    test_case: SnowflakeConnectConfigTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object]
    raw_connection: FakeSnowflakeRawConnection
    captured_kwargs, raw_connection = install_fake_snowflake_connector(monkeypatch)
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    adapter.connect(test_case.config)

    assert captured_kwargs == test_case.expected_connect_kwargs
    assert tuple(raw_connection.executed_sql) == test_case.expected_session_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeInvalidSecondaryRolesTestCase(
            description="named role is not a supported secondary-role mode",
            secondary_roles="TRANSFORMER",
            expected_error="secondary_roles must be 'ALL' or 'NONE'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_secondary_roles_when_connecting_then_fails_before_opening_connection(
    test_case: SnowflakeInvalidSecondaryRolesTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs, _ = install_fake_snowflake_connector(monkeypatch)
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    with pytest.raises(AdapterUserError, match=test_case.expected_error):
        adapter.connect({"account": "acct", "secondary_roles": test_case.secondary_roles})

    assert captured_kwargs == {}


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeInformationSchemaFilterTestCase(
            description="uppercases relation schema filter bind values",
            database="RACING",
            schemas=("staging",),
            names=("race__stg_horse",),
            expected_params=("STAGING", "RACE__STG_HORSE", "RACING"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lowercase_schema_when_listing_relations_then_uppercases_filter_bind_values(
    test_case: SnowflakeInformationSchemaFilterTestCase,
) -> None:
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(
        rows=[("RACE__STG_HORSE", "STAGING", "BASE TABLE", "YES")]
    )
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    relations: tuple[Any, ...] = adapter.list_relations(
        connection=cast(Any, connection),
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )

    assert cursor.executed_params == test_case.expected_params
    assert cursor.executed_sql is not None
    assert "UPPER(table_" not in cursor.executed_sql
    assert len(relations) == 1
    assert relations[0].schema == "staging"
    assert relations[0].name == "race__stg_horse"
    assert relations[0].is_transient is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeInformationSchemaFilterTestCase(
            description="uppercases relation existence filter bind values",
            database="racing",
            schemas=("staging",),
            names=("race__stg_horse",),
            expected_params=("RACE__STG_HORSE", "STAGING", "RACING"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lowercase_schema_when_checking_relation_exists_then_uses_sargable_filters(
    test_case: SnowflakeInformationSchemaFilterTestCase,
) -> None:
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(row=(1,))
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    exists: bool = adapter.relation_exists(
        connection=cast(Any, connection),
        database=test_case.database,
        schema=test_case.schemas[0],
        name=test_case.names[0],
    )

    assert exists is True
    assert cursor.executed_sql is not None
    assert "UPPER(table_" not in cursor.executed_sql
    assert cursor.executed_params == test_case.expected_params


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeInformationSchemaFilterTestCase(
            description="uppercases column schema filter bind values",
            database="RACING",
            schemas=("staging",),
            names=("race__stg_horse",),
            expected_params=("STAGING", "RACE__STG_HORSE", "RACING"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lowercase_schema_when_getting_all_columns_then_uppercases_filter_bind_values(
    test_case: SnowflakeInformationSchemaFilterTestCase,
) -> None:
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(
        rows=[("RACE__STG_HORSE", "ID", "NUMBER", 38, 0, None)]
    )
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection=cast(Any, connection),
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )

    assert cursor.executed_params == test_case.expected_params
    assert cursor.executed_sql is not None
    assert "UPPER(table_" not in cursor.executed_sql
    assert tuple(columns) == ("race__stg_horse",)
    assert columns["race__stg_horse"][0].name == "id"


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeQualifiedColumnInspectionTestCase(
            description="32 mixed relations use exact SHOW and match bulk normalization",
            relation_count=32,
            expected_statement_count=32,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_32_mixed_relations_when_getting_columns_then_exact_and_bulk_are_equivalent(
    test_case: SnowflakeQualifiedColumnInspectionTestCase,
) -> None:
    relations: tuple[RelationInfo, ...] = build_qualified_column_relations(
        count=test_case.relation_count
    )
    ordered_relations: tuple[RelationInfo, ...] = tuple(
        sorted(relations, key=lambda relation: tuple(part or "" for part in relation.identity))
    )
    exact_connection: FakeSnowflakeMetadataSequenceConnection = (
        FakeSnowflakeMetadataSequenceConnection(
            tuple(
                FakeSnowflakeMetadataCursor(rows=build_show_columns_rows(relation=relation))
                for relation in ordered_relations
            )
        )
    )
    bulk_cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(
        rows=build_bulk_columns_rows(relations=relations)
    )
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    exact_columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(
            connection=cast(Any, exact_connection), relations=relations
        )
    )
    bulk_columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter._get_columns_for_relations_bulk(
            connection=cast(Any, FakeSnowflakeMetadataConnection(bulk_cursor)),
            relations=relations,
        )
    )

    executed_sql: tuple[str, ...] = tuple(
        cursor.executed_sql or "" for cursor in exact_connection.returned_cursors
    )
    assert len(executed_sql) == test_case.expected_statement_count
    assert any("SHOW COLUMNS IN TABLE" in sql for sql in executed_sql)
    assert any("SHOW COLUMNS IN VIEW" in sql for sql in executed_sql)
    assert exact_columns == expected_qualified_columns(relations=relations)
    assert bulk_columns == exact_columns
    assert ("racing", "schema_a", "shared") in exact_columns
    assert ("racing", "schema_b", "shared") in exact_columns


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeQualifiedColumnInspectionTestCase(
            description="33 mixed relations use one database-qualified bulk query",
            relation_count=33,
            expected_statement_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_33_mixed_relations_when_getting_columns_then_uses_bulk_query(
    test_case: SnowflakeQualifiedColumnInspectionTestCase,
) -> None:
    relations: tuple[RelationInfo, ...] = build_qualified_column_relations(
        count=test_case.relation_count
    )
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(
        rows=build_bulk_columns_rows(relations=relations)
    )
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(
            connection=cast(Any, FakeSnowflakeMetadataConnection(cursor)), relations=relations
        )
    )

    assert cursor.executed_sql is not None
    assert test_case.expected_statement_count == 1
    assert 'FROM "RACING".information_schema.columns' in cursor.executed_sql
    assert "table_schema = %s AND table_name IN" in cursor.executed_sql
    assert columns == expected_qualified_columns(relations=relations)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeQualifiedColumnInspectionTestCase(
            description="251 relations use two bounded bulk queries and merge all results",
            relation_count=251,
            expected_statement_count=2,
        ),
        SnowflakeQualifiedColumnInspectionTestCase(
            description="1000 relations use five bounded bulk queries and merge all results",
            relation_count=1000,
            expected_statement_count=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_relation_set_when_getting_columns_then_chunks_and_merges_bulk_results(
    test_case: SnowflakeQualifiedColumnInspectionTestCase,
) -> None:
    relations: tuple[RelationInfo, ...] = build_qualified_column_relations(
        count=test_case.relation_count
    )
    ordered_relations: tuple[RelationInfo, ...] = tuple(
        sorted(relations, key=lambda relation: tuple(part or "" for part in relation.identity))
    )
    connection: FakeSnowflakeMetadataSequenceConnection = build_bulk_sequence_connection(
        relations=ordered_relations, chunk_size=200
    )

    columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        SnowflakeAdapter().get_columns_for_relations(
            connection=cast(Any, connection), relations=relations
        )
    )

    assert len(connection.returned_cursors) == test_case.expected_statement_count
    assert columns == expected_qualified_columns(relations=relations)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakePruneSqlTestCase(
            description="renders fingerprint pruning with delete using ranked stale rows",
            database=None,
            schema="ANALYTICS",
            retain_versions=5,
            expected_fragments=(
                "DELETE FROM ANALYTICS._sqlbuild_fingerprints AS target USING",
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "__sqlbuild_history_rank > 5",
                "target.node_type = stale.node_type",
                "target.node_name = stale.node_name",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_table_when_rendering_prune_then_snowflake_uses_history_rank(
    test_case: SnowflakePruneSqlTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    sql: str = adapter.render_prune_fingerprint_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakePruneSqlTestCase(
            description="renders source freshness pruning with null-safe full identity",
            database=None,
            schema="ANALYTICS",
            retain_versions=3,
            expected_fragments=(
                "DELETE FROM ANALYTICS._sqlbuild_source_freshness AS target USING",
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "__sqlbuild_history_rank > 3",
                "EQUAL_NULL(target.target_database, stale.target_database)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_table_when_rendering_prune_then_snowflake_uses_history_rank(
    test_case: SnowflakePruneSqlTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    sql: str = adapter.render_prune_source_freshness_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderCursorBoundLiteralTestCase(
            description="renders timestamp cursor bounds as typed literals",
            value="2024-01-15T00:00:00",
            cursor_type=CursorKind.TIMESTAMP,
            expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
        ),
        SnowflakeRenderCursorBoundLiteralTestCase(
            description="renders integer cursor bounds without quotes",
            value="42",
            cursor_type=CursorKind.INTEGER,
            expected_literal="42",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_bounds_when_rendering_then_snowflake_returns_expected_literal(
    test_case: SnowflakeRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    result: str = adapter.render_cursor_bound_literal(
        value=test_case.value, cursor_type=test_case.cursor_type
    )

    assert result == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderCloneTestCase(
            description="renders zero copy table clone by default",
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            origin_is_transient=False,
            expected_statements=("CREATE OR REPLACE TABLE dev.fact_orders CLONE prod.fact_orders",),
            expected_supports_zero_copy=True,
        ),
        SnowflakeRenderCloneTestCase(
            description="renders transient clone when origin is transient",
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            origin_is_transient=True,
            expected_statements=(
                "CREATE OR REPLACE TRANSIENT TABLE dev.fact_orders CLONE prod.fact_orders",
            ),
            expected_supports_zero_copy=True,
        ),
        SnowflakeRenderCloneTestCase(
            description="renders transient CTAS when hard copy is requested",
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=True,
            origin_is_transient=False,
            expected_statements=(
                "CREATE OR REPLACE TRANSIENT TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
            expected_supports_zero_copy=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_request_when_rendering_then_snowflake_uses_expected_clone_sql(
    test_case: SnowflakeRenderCloneTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_clone(
        origin=test_case.source,
        destination=test_case.target,
        hard_copy=test_case.hard_copy,
        origin_is_transient=test_case.origin_is_transient,
    )

    assert adapter.supports_zero_copy_clone() is test_case.expected_supports_zero_copy
    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeMoveOrCopyRelationTestCase(
            description="moves table across schemas with native rename",
            source="ANALYTICS.MARTS.FACT_ORDERS",
            target="ANALYTICS.MARTS__SQB_PHYSICAL.FACT_ORDERS__V_ABC123",
            expected_statements=(
                "ALTER TABLE ANALYTICS.MARTS.FACT_ORDERS "
                "RENAME TO ANALYTICS.MARTS__SQB_PHYSICAL.FACT_ORDERS__V_ABC123",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cross_schema_table_move_when_moving_then_snowflake_uses_native_rename(
    test_case: SnowflakeMoveOrCopyRelationTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(())
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.move_or_copy_relation(
        connection=connection,
        origin=test_case.source,
        destination=test_case.target,
        remove_origin=True,
        allow_copy_fallback=False,
        statement_recorder=statement_recorder,
    )

    assert tuple(connection.executed_sql) == test_case.expected_statements
    assert tuple(event.content for event in statement_recorder.snapshot()) == (
        test_case.expected_statements
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderIdentifierTestCase(
            description="uppercases logical lowercase identifiers before quoting",
            name="event_id",
            expected_identifier='"EVENT_ID"',
        ),
        SnowflakeRenderIdentifierTestCase(
            description="escapes quotes after applying Snowflake uppercase semantics",
            name='event"id',
            expected_identifier='"EVENT""ID"',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_identifier_when_rendering_then_snowflake_quotes_uppercase_identifier(
    test_case: SnowflakeRenderIdentifierTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    identifier: str = adapter.render_identifier(test_case.name)

    assert identifier == test_case.expected_identifier


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeMergeExclusionTestCase(
            description="snowflake selective merge",
            expected_update_assignment='"STATUS" = __source."STATUS"',
            expected_insert_clause=(
                ' ("TENANT_ID", "ORDER_ID", "STATUS", "UPDATED_AT") VALUES '
                '(__source."TENANT_ID", __source."ORDER_ID", __source."STATUS", '
                '__source."UPDATED_AT")'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_composite_key_and_case_different_exclusion_when_rendering_merge_then_updates_only_mutable_columns(  # noqa: E501
    test_case: SnowflakeMergeExclusionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    rendered_sql: str = adapter.render_merge(
        destination="ANALYTICS.ORDERS",
        sql="SELECT tenant_id, order_id, status, updated_at FROM DELTA_ORDERS",
        unique_key=("tenant_id", "order_id"),
        source_columns=("tenant_id", "order_id", "status", "updated_at"),
        exclude_columns=("UPDATED_AT",),
    )[0]
    update_clause, insert_clause = rendered_sql.split("WHEN NOT MATCHED THEN INSERT", maxsplit=1)
    update_assignments: str = update_clause.split("WHEN MATCHED THEN UPDATE SET", maxsplit=1)[1]

    assert '"TENANT_ID" = __source."TENANT_ID"' not in update_assignments
    assert '"ORDER_ID" = __source."ORDER_ID"' not in update_assignments
    assert '"UPDATED_AT" = __source."UPDATED_AT"' not in update_assignments
    assert test_case.expected_update_assignment in update_assignments
    assert insert_clause == test_case.expected_insert_clause


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableFreshnessMetadataTestCase(
            description="returns last altered for physical table",
            row=("BASE TABLE", datetime(2026, 1, 2, 3, 4, 5)),
            expected_data_version=datetime(2026, 1, 2, 3, 4, 5),
            expected_value_kind="timestamp",
            expected_supports_metadata=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_physical_table_when_getting_freshness_metadata_then_returns_last_altered(
    test_case: SnowflakeTableFreshnessMetadataTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(test_case.row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)

    metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection=connection,
        database="ANALYTICS",
        schema="RAW",
        name="ORDERS",
    )

    assert adapter.supports_table_freshness_metadata() is test_case.expected_supports_metadata
    assert metadata.data_version == test_case.expected_data_version
    assert metadata.value_kind == test_case.expected_value_kind
    assert metadata.observed_at == test_case.expected_data_version
    assert cursor.executed_sql is not None
    assert "UPPER(table_" not in cursor.executed_sql
    assert "information_schema.tables" in cursor.executed_sql
    assert "last_altered" in cursor.executed_sql
    assert cursor.executed_params == ("ORDERS", "RAW", "ANALYTICS")
    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableFreshnessBatchTestCase(
            description="returns last altered for multiple physical tables",
            expected_data_versions=(
                datetime(2026, 1, 2, 3, 4, 5),
                datetime(2026, 1, 3, 4, 5, 6),
            ),
            expected_query_fragments=(
                "SELECT table_catalog, table_schema, table_name, table_type, last_altered",
                "table_catalog = %s",
                "table_schema = %s",
                "table_name IN (%s, %s)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_physical_tables_when_getting_freshness_metadata_then_batches_last_altered(
    test_case: SnowflakeTableFreshnessBatchTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    requests: tuple[TableFreshnessRequest, ...] = (
        TableFreshnessRequest(database="ANALYTICS", schema="RAW", name="ORDERS"),
        TableFreshnessRequest(database="ANALYTICS", schema="RAW", name="CUSTOMERS"),
    )
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(
        rows=[
            ("ANALYTICS", "RAW", "ORDERS", "BASE TABLE", test_case.expected_data_versions[0]),
            ("ANALYTICS", "RAW", "CUSTOMERS", "BASE TABLE", test_case.expected_data_versions[1]),
        ]
    )
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)

    metadata_by_request: dict[TableFreshnessRequest, TableFreshnessMetadata] = (
        adapter.get_tables_freshness_metadata(connection=connection, requests=requests)
    )

    assert (
        tuple(metadata_by_request[request].data_version for request in requests)
        == test_case.expected_data_versions
    )
    assert all(metadata.value_kind == "timestamp" for metadata in metadata_by_request.values())
    assert cursor.executed_sql is not None
    for fragment in test_case.expected_query_fragments:
        assert fragment in cursor.executed_sql
    assert "UPPER(table_" not in cursor.executed_sql
    assert " OR " not in cursor.executed_sql
    assert cursor.executed_params == ("ANALYTICS", "RAW", "ORDERS", "CUSTOMERS")
    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableFreshnessMetadataErrorTestCase(
            description="raises when metadata row is missing",
            row=None,
            expected_error_fragment="not found",
        ),
        SnowflakeTableFreshnessMetadataErrorTestCase(
            description="raises when relation is a view",
            row=("VIEW", datetime(2026, 1, 2, 3, 4, 5)),
            expected_error_fragment="only supports physical tables",
        ),
        SnowflakeTableFreshnessMetadataErrorTestCase(
            description="raises when last altered is missing",
            row=("BASE TABLE", None),
            expected_error_fragment="missing LAST_ALTERED",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_relation_when_getting_freshness_metadata_then_raises_clear_error(
    test_case: SnowflakeTableFreshnessMetadataErrorTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(test_case.row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        adapter.get_table_freshness_metadata(
            connection=connection,
            database="ANALYTICS",
            schema="RAW",
            name="ORDERS",
        )

    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderPythonFunctionTestCase(
            description="renders Python UDF DDL with runtime handler and packages",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION "
                "udf_db.udf_schema.is_positive_int(a_string STRING)\n"
                "RETURNS INTEGER\n"
                "LANGUAGE PYTHON\n"
                "RUNTIME_VERSION = '3.11'\n"
                "HANDLER = 'main'\n"
                "PACKAGES = ('numpy','pandas==1.5.0')\n"
                "AS $$\n"
                "def main(a_string):\n"
                "    return 1 if a_string else 0\n"
                "$$"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_function_when_rendering_then_snowflake_returns_expected_ddl(
    test_case: SnowflakeRenderPythonFunctionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="udf_db.udf_schema.is_positive_int",
        arguments=(FunctionArgument(name="a_string", type="STRING"),),
        returns="INTEGER",
        body_sql="def main(a_string):\n    return 1 if a_string else 0",
        language=FunctionLanguage.PYTHON,
        runtime_version="3.11",
        entry_point="main",
        packages=("numpy", "pandas==1.5.0"),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderTableFunctionTestCase(
            description="renders table function DDL with explicit Snowflake return columns",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION analytics.customer_orders(p_customer_id INTEGER)\n"
                "RETURNS TABLE (order_id INTEGER)\n"
                "AS $$\nSELECT order_id FROM analytics.fact_orders\n"
                "WHERE customer_id = p_customer_id\n$$"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_when_rendering_then_snowflake_returns_expected_ddl(
    test_case: SnowflakeRenderTableFunctionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="analytics.customer_orders",
        arguments=(FunctionArgument(name="p_customer_id", type="INTEGER"),),
        returns="TABLE",
        body_sql=("SELECT order_id FROM analytics.fact_orders\nWHERE customer_id = p_customer_id"),
        return_columns=(FunctionReturnColumn(name="order_id", type="INTEGER"),),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeSchemaDiffTestCase(
            description="treats semantically equivalent numeric types as unchanged",
            expected_result=SchemaDiffResult(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equivalent_types_when_diffing_schema_then_snowflake_ignores_alias_only_changes(
    test_case: SnowflakeSchemaDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    monkeypatch.setattr(
        adapter,
        "describe_relation",
        describe_equivalent_numeric_relation,
    )

    result: SchemaDiffResult = adapter.diff_schema(
        connection=object(),
        left="left_relation",
        right="right_relation",
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeQueryColumnNamesTestCase(
            description="preserves Snowflake cursor output column names",
            cursor_description=(("ID",), ("FIRST_NAME",), ("CREATED_AT",)),
            expected_columns=("ID", "FIRST_NAME", "CREATED_AT"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_query_metadata_when_getting_column_names_then_preserves_cursor_names(
    test_case: SnowflakeQueryColumnNamesTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(
        description=test_case.cursor_description
    )
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)

    columns: tuple[str, ...] = adapter.query_column_names(
        connection=connection,
        sql="SELECT 1 AS id, 'Ada' AS first_name, CURRENT_TIMESTAMP AS created_at",
    )

    assert columns == test_case.expected_columns
    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeLoadSeedTestCase(
            description="loads seed with default quote character",
            csv_text='id,name\n1,"Liege waffle"\n',
            expected_rows=[("1", "Liege waffle")],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_default_seed_csv_settings_when_loading_seed_then_uses_python_csv_defaults(
    test_case: SnowflakeLoadSeedTestCase,
    tmp_path: Path,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(description=())
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)
    seed_file: Path = tmp_path / "waffle_types.csv"
    seed_file.write_text(test_case.csv_text, encoding="utf-8")

    adapter.load_seed(
        connection=connection,
        destination="dev.waffle_types",
        file_path=seed_file,
        columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        replace=False,
        statement_recorder=StatementRecorder(),
    )

    assert cursor.executemany_rows == test_case.expected_rows
