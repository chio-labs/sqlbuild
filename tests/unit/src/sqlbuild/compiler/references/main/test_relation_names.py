"""Relation-name extraction and project-relation matching for hard-coded name checks."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.main.match_project_relation import match_project_relation
from sqlbuild.compiler.references.models import (
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.refs import model, source
from tests.unit.src.sqlbuild.compiler.references.main._test_types import (
    ExtractRelationNamesTestCase,
    MatchProjectRelationTestCase,
    UnparseableRelationNamesTestCase,
)

_INDEX: ProjectRelationIndex = ProjectRelationIndex(
    relations=(
        ProjectRelation(
            ref=model("customers"),
            relation=RelationName(name="customers", schema="analytics", database="warehouse"),
        ),
        ProjectRelation(
            ref=source("raw_orders"), relation=RelationName(name="orders", schema="raw")
        ),
    )
)


@pytest.mark.parametrize(
    "test_case",
    (
        ExtractRelationNamesTestCase(
            description="select, join, and CTE names",
            sql="WITH recent AS (SELECT 1) SELECT * FROM recent JOIN analytics.customers c ON 1=1",
            dialect="duckdb",
            expected_relations=(RelationName(name="customers", schema="analytics"),),
        ),
        ExtractRelationNamesTestCase(
            description="DML targets across statements and temporary tables",
            sql=(
                "CREATE TEMP TABLE staged AS SELECT 1 AS id; "
                "DELETE FROM warehouse.analytics.customers WHERE id IN (SELECT id FROM staged)"
            ),
            dialect="duckdb",
            expected_relations=(
                RelationName(name="staged"),
                RelationName(name="customers", schema="analytics", database="warehouse"),
            ),
            expected_temporary=frozenset({"staged"}),
        ),
        ExtractRelationNamesTestCase(
            description="quoted dotted path splits into qualifier parts",
            sql="SELECT * FROM `warehouse.analytics.customers`",
            dialect="bigquery",
            expected_relations=(
                RelationName(name="customers", schema="analytics", database="warehouse"),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_when_extracting_relation_names_then_returns_named_relations(
    test_case: ExtractRelationNamesTestCase,
) -> None:
    extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = extract_relation_names(
        sql=test_case.sql, dialect=test_case.dialect
    )

    assert extracted is not None
    assert set(extracted[0]) == set(test_case.expected_relations)
    assert extracted[1] == test_case.expected_temporary


@pytest.mark.parametrize(
    "test_case",
    (
        UnparseableRelationNamesTestCase(
            description="malformed select", sql="SELEC FROM ((", expected_result=None
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unparseable_sql_when_extracting_relation_names_then_returns_none(
    test_case: UnparseableRelationNamesTestCase,
) -> None:
    assert extract_relation_names(sql=test_case.sql, dialect="duckdb") is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (
        MatchProjectRelationTestCase(
            description="unqualified name resolved against the matching current schema",
            relation=RelationName(name="CUSTOMERS"),
            default_schema="analytics",
            expected_ref=model("customers"),
        ),
        MatchProjectRelationTestCase(
            description="unqualified name in another current schema",
            relation=RelationName(name="customers"),
            default_schema="staging",
            expected_ref=None,
        ),
        MatchProjectRelationTestCase(
            description="qualified source table",
            relation=RelationName(name="orders", schema="raw"),
            default_schema="analytics",
            expected_ref=source("raw_orders"),
        ),
        MatchProjectRelationTestCase(
            description="non-project relation",
            relation=RelationName(name="tables", schema="information_schema"),
            default_schema="analytics",
            expected_ref=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relation_when_matching_project_relations_then_resolves_missing_qualifiers(
    test_case: MatchProjectRelationTestCase,
) -> None:
    match: ProjectRelation | None = match_project_relation(
        index=_INDEX, relation=test_case.relation, default_schema=test_case.default_schema
    )

    assert getattr(match, "ref", None) == test_case.expected_ref


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
