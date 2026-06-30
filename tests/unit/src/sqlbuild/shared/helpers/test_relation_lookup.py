from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.shared.models import RelationLookup
from tests.unit.src.sqlbuild.shared.helpers._test_types import RelationLookupTestCase
from tests.unit.src.sqlbuild.shared.helpers.helpers import RecordingRelationAdapter

RELATION_LOOKUP_TEST_CASES: list[RelationLookupTestCase] = [
    RelationLookupTestCase(
        description="gathers one database in a single batched call and finds a transient relation",
        warehouse_relations=(
            (None, "fact_orders", True),
            (None, "dim_customers", False),
        ),
        locations=(
            (None, "marts", "fact_orders"),
            (None, "marts", "dim_customers"),
            (None, "staging", "fact_orders"),
        ),
        probe_schema="marts",
        probe_name="fact_orders",
        expected_exists=True,
        expected_is_transient=True,
        expected_list_relations_calls=1,
        expected_queried_relation_calls=((None, ("marts", "staging")),),
    ),
    RelationLookupTestCase(
        description="absent relation reports not-existing and not-transient",
        warehouse_relations=((None, "fact_orders", True),),
        locations=((None, "marts", "fact_orders"),),
        probe_schema="marts",
        probe_name="missing_model",
        expected_exists=False,
        expected_is_transient=False,
        expected_list_relations_calls=1,
        expected_queried_relation_calls=((None, ("marts",)),),
    ),
    RelationLookupTestCase(
        description="schema wildcard queries by name and finds relation in any schema",
        warehouse_relations=((None, "fact_orders", True),),
        locations=((None, None, "fact_orders"),),
        probe_schema=None,
        probe_name="fact_orders",
        expected_exists=True,
        expected_is_transient=True,
        expected_list_relations_calls=1,
        expected_queried_relation_calls=((None, ()),),
    ),
    RelationLookupTestCase(
        description="keeps same schema and name separate across databases",
        warehouse_relations=(
            ("prod", "fact_orders", True),
            ("dev", "fact_orders", False),
        ),
        locations=(
            ("prod", "marts", "fact_orders"),
            ("dev", "marts", "fact_orders"),
        ),
        probe_database="dev",
        probe_schema="marts",
        probe_name="fact_orders",
        expected_exists=True,
        expected_is_transient=False,
        expected_list_relations_calls=2,
        expected_queried_relation_calls=(
            ("prod", ("marts",)),
            ("dev", ("marts",)),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RELATION_LOOKUP_TEST_CASES,
    ids=[case.description for case in RELATION_LOOKUP_TEST_CASES],
)
def test_given_locations_when_building_relation_lookup_then_batches_and_answers_queries(
    test_case: RelationLookupTestCase,
) -> None:
    adapter: RecordingRelationAdapter = RecordingRelationAdapter(
        relations=tuple(
            RelationInfo(
                database=database,
                schema="marts",
                name=name,
                relation_type="base table",
                is_transient=is_transient,
            )
            for database, name, is_transient in test_case.warehouse_relations
        )
    )

    lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=object(),
        locations=test_case.locations,
    )

    assert (
        lookup.exists(
            database=test_case.probe_database,
            schema=test_case.probe_schema,
            name=test_case.probe_name,
        )
        == test_case.expected_exists
    )
    assert (
        lookup.is_transient(
            database=test_case.probe_database,
            schema=test_case.probe_schema,
            name=test_case.probe_name,
        )
        == test_case.expected_is_transient
    )
    assert len(adapter.list_relations_calls) == test_case.expected_list_relations_calls
    assert tuple(adapter.list_relations_calls) == test_case.expected_queried_relation_calls
