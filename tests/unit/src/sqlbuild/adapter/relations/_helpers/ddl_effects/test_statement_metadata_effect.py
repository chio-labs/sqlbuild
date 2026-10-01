"""Executed SQL is classified conservatively by its effect on cached relation metadata."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.relations._helpers.ddl_effects import statement_metadata_effect
from sqlbuild.adapter.relations.models import StatementMetadataEffect
from tests.unit.src.sqlbuild.adapter.relations._helpers.ddl_effects._test_types import (
    StatementMetadataEffectTestCase,
)

_NONE: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    "test_case",
    [
        StatementMetadataEffectTestCase(
            description="create or replace transient table as select",
            sql="CREATE OR REPLACE TRANSIENT TABLE analytics.marts.orders__delta AS SELECT 1 AS id",
            expected_relation_names=frozenset({"orders__delta"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="quoted three-part view",
            sql='CREATE OR REPLACE VIEW "ANALYTICS"."MARTS"."ORDERS_V" AS SELECT 1 AS id',
            expected_relation_names=frozenset({"orders_v"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="clone names only the new relation",
            sql="CREATE TABLE marts.orders__prev CLONE marts.orders",
            expected_relation_names=frozenset({"orders__prev"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="drop table if exists",
            sql="DROP TABLE IF EXISTS analytics.marts.orders__delta",
            expected_relation_names=frozenset({"orders__delta"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="rename names both relations",
            sql="ALTER TABLE marts.orders__stage RENAME TO marts.orders",
            expected_relation_names=frozenset({"orders__stage", "orders"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="swap names both relations",
            sql="ALTER TABLE analytics.marts.orders SWAP WITH analytics.marts.orders__stage",
            expected_relation_names=frozenset({"orders", "orders__stage"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="add column after a leading comment",
            sql='-- schema change\nALTER TABLE marts.orders ADD COLUMN "NOTE" VARCHAR',
            expected_relation_names=frozenset({"orders"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="column rename is not a relation rename",
            sql='ALTER TABLE marts.orders RENAME COLUMN "OLD" TO "NEW"',
            expected_relation_names=frozenset({"orders"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="backtick qualified name",
            sql="CREATE OR REPLACE TABLE `project.dataset.orders` AS SELECT 1 AS id",
            expected_relation_names=frozenset({"orders"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="bracket qualified name",
            sql="DROP TABLE IF EXISTS [dbo].[orders__delta]",
            expected_relation_names=frozenset({"orders__delta"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="quoted dotted name keeps its dot like a lookup name",
            sql='CREATE TABLE "s"."my.table" (id INT)',
            expected_relation_names=frozenset({"my.table"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="statement separator inside a literal is data",
            sql="CREATE OR REPLACE TABLE marts.notes AS SELECT 'a;b -- c' AS note",
            expected_relation_names=frozenset({"notes"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="escaped backslash literal reads the same either way",
            sql="CREATE OR REPLACE TABLE marts.codes AS SELECT REGEXP_LIKE(code, '\\\\d+') AS ok",
            expected_relation_names=frozenset({"codes"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="select into creates a table",
            sql="SELECT * INTO [dbo].[orders__staging] FROM (SELECT 1 AS id) AS __create_source",
            expected_relation_names=frozenset({"orders__staging"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="common table expression select into creates a table",
            sql="WITH v AS (SELECT 1 AS id) SELECT id INTO dbo.orders_history FROM v",
            expected_relation_names=frozenset({"orders_history"}),
            expected_invalidates_all=False,
        ),
        StatementMetadataEffectTestCase(
            description="copy into a table may evolve its columns",
            sql="COPY INTO raw.orders FROM @landing/orders",
            expected_relation_names=frozenset({"orders"}),
            expected_invalidates_all=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_targeted_ddl_statement_when_classifying_then_reports_possible_metadata_changes(
    test_case: StatementMetadataEffectTestCase,
) -> None:
    effect: StatementMetadataEffect = statement_metadata_effect(test_case.sql)

    assert effect.relation_names == test_case.expected_relation_names
    assert effect.invalidates_all is test_case.expected_invalidates_all
    assert effect.ends_transaction is test_case.expected_ends_transaction


@pytest.mark.parametrize(
    "test_case",
    [
        StatementMetadataEffectTestCase(
            description=sql.split()[0].lower() + " " + str(index),
            sql=sql,
            expected_relation_names=_NONE,
            expected_invalidates_all=False,
        )
        for index, sql in enumerate(
            (
                "SELECT COUNT(*) FROM marts.orders__delta",
                "WITH totals AS (SELECT 1 AS id) SELECT * FROM totals",
                "SHOW COLUMNS IN TABLE analytics.marts.orders",
                "INSERT INTO marts.orders (id) SELECT id FROM marts.orders__delta",
                "MERGE INTO marts.orders AS t USING (SELECT 1 AS id) AS s ON t.id = s.id",
                "DELETE FROM marts.orders WHERE id = 1",
                "BEGIN",
                "CREATE SCHEMA IF NOT EXISTS analytics.marts",
                "CREATE OR REPLACE FUNCTION marts.add_one(x NUMBER) RETURNS NUMBER AS $$ x + 1 $$",
                "TRUNCATE TABLE marts.orders",
                "CREATE OR REPLACE FUNCTION f() RETURNS INT AS $$ SELECT 1; SELECT 2 $$",
                "INSERT INTO marts.notes VALUES ('drop table u; --')",
            )
        )
    ],
    ids=lambda case: case.description,
)
def test_given_read_or_data_statement_when_classifying_then_reports_possible_metadata_changes(
    test_case: StatementMetadataEffectTestCase,
) -> None:
    effect: StatementMetadataEffect = statement_metadata_effect(test_case.sql)

    assert effect.relation_names == test_case.expected_relation_names
    assert effect.invalidates_all is test_case.expected_invalidates_all
    assert effect.ends_transaction is test_case.expected_ends_transaction


@pytest.mark.parametrize(
    "test_case",
    [
        StatementMetadataEffectTestCase(
            description=description,
            sql=sql,
            expected_relation_names=_NONE,
            expected_invalidates_all=True,
        )
        for description, sql in (
            ("procedure call", "CALL marts.rebuild_orders()"),
            ("replace schema drops its relations", "CREATE OR REPLACE SCHEMA analytics.marts"),
            ("drop schema", "DROP SCHEMA IF EXISTS analytics.marts"),
            ("multi statement", "INSERT INTO marts.orders VALUES (1); DROP TABLE marts.orders"),
            ("dynamic sql", "EXECUTE IMMEDIATE 'DROP TABLE marts.orders'"),
            (
                "session schema change re-resolves unqualified lookups",
                "USE SCHEMA analytics.staging",
            ),
            ("session parameters may change identifier resolution", "ALTER SESSION SET X = 1"),
            ("unparseable relation name", 'CREATE TABLE "unterminated AS SELECT 1'),
            ("empty statement", "   "),
            ("keyword before the relation name", 'ALTER TABLE ONLY "s"."t" ADD COLUMN c INT'),
            ("several dropped relations", "DROP TABLE IF EXISTS a, b"),
            ("unquoted non-ascii name", "CREATE TABLE s.café (id INT)"),
            ("comment marker inside a literal hides nothing", "SELECT 'a--b'; DROP TABLE u"),
            ("separator after a literal", "INSERT INTO t VALUES ('x'); DROP TABLE u"),
            (
                "backslash-escaped quote is ambiguous",
                "SELECT 'a\\' AS x FROM t WHERE y = '; DROP TABLE u'",
            ),
            ("unterminated literal", "CREATE TABLE t AS SELECT 'open"),
            (
                "unexpected clause after the name",
                "CREATE DYNAMIC TABLE t TARGET_LAG = '1 hour' AS SELECT 1",
            ),
            ("rename target followed by more text", "ALTER TABLE a RENAME TO b c"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unbounded_statement_when_classifying_then_reports_possible_metadata_changes(
    test_case: StatementMetadataEffectTestCase,
) -> None:
    effect: StatementMetadataEffect = statement_metadata_effect(test_case.sql)

    assert effect.relation_names == test_case.expected_relation_names
    assert effect.invalidates_all is test_case.expected_invalidates_all
    assert effect.ends_transaction is test_case.expected_ends_transaction


@pytest.mark.parametrize(
    "test_case",
    [
        StatementMetadataEffectTestCase(
            description=sql.lower(),
            sql=sql,
            expected_relation_names=_NONE,
            expected_invalidates_all=False,
            expected_ends_transaction=True,
        )
        for sql in ("COMMIT", "ROLLBACK")
    ],
    ids=lambda case: case.description,
)
def test_given_transaction_end_statement_when_classifying_then_reports_possible_metadata_changes(
    test_case: StatementMetadataEffectTestCase,
) -> None:
    effect: StatementMetadataEffect = statement_metadata_effect(test_case.sql)

    assert effect.relation_names == test_case.expected_relation_names
    assert effect.invalidates_all is test_case.expected_invalidates_all
    assert effect.ends_transaction is test_case.expected_ends_transaction


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
