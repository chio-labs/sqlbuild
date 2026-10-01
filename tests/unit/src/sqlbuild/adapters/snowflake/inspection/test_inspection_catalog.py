"""Catalog-served Snowflake metadata must equal what the adapter returns directly."""

from __future__ import annotations

from collections import Counter

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    RelationInfo,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog
from sqlbuild.adapter.relations.constants import INSPECTION_IN_LIST_LIMIT
from sqlbuild.adapter.relations.main.open_inspection_catalog import open_inspection_catalog
from tests.unit.src.sqlbuild.adapters.snowflake.inspection._test_types import (
    ColumnRequestEquivalenceTestCase,
    FreshnessErrorTestCase,
    FreshnessReuseTestCase,
    RelationRequestEquivalenceTestCase,
    RepeatedLookupTestCase,
    SpeculativePrefetchTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
    build_inspection_catalog_relations,
    build_offline_snowflake,
    sorted_relation_reprs,
)

_MANY_NAMES: tuple[str, ...] = (
    "orders",
    "customers_v",
    *(f"inventory_{index}" for index in range(INSPECTION_IN_LIST_LIMIT + 10)),
)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationRequestEquivalenceTestCase(
            description="whole schema with case variants, views, transient and external tables",
            database="analytics",
            schemas=("staging",),
            names=None,
            expected_relation_count=47,
        ),
        RelationRequestEquivalenceTestCase(
            description="name filter across schemas ignores quoted lowercase twins",
            database="analytics",
            schemas=("staging", "marts"),
            names=("orders", "orderlines", "customers_v", "revenue_v", "missing"),
            expected_relation_count=2,
        ),
        RelationRequestEquivalenceTestCase(
            description="uppercase request matches unquoted storage",
            database="ANALYTICS",
            schemas=("STAGING",),
            names=("ORDERS",),
            expected_relation_count=1,
        ),
        RelationRequestEquivalenceTestCase(
            description="quoted mixed-case schema is not matched by a logical name",
            database="analytics",
            schemas=("mixed_case",),
            names=None,
            expected_relation_count=0,
        ),
        RelationRequestEquivalenceTestCase(
            description="session database lists every catalog",
            database=None,
            schemas=("staging",),
            names=("orders",),
            expected_relation_count=2,
        ),
        RelationRequestEquivalenceTestCase(
            description="database-wide name lookup",
            database="analytics",
            schemas=None,
            names=("orders", "revenue"),
            expected_relation_count=2,
        ),
        RelationRequestEquivalenceTestCase(
            description="database-wide lookup beyond the IN-list cap is chunked",
            database="analytics",
            schemas=None,
            names=_MANY_NAMES,
            expected_relation_count=42,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_metadata_request_when_served_by_catalog_then_matches_direct_adapter(
    test_case: RelationRequestEquivalenceTestCase,
) -> None:
    adapter, connection, warehouse = build_offline_snowflake(
        relations=build_inspection_catalog_relations()
    )
    direct: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )
    warehouse.reset()

    served: tuple[RelationInfo, ...] = InspectionCatalog(
        adapter=adapter, connection=connection
    ).list_relations(database=test_case.database, schemas=test_case.schemas, names=test_case.names)

    assert len(served) == test_case.expected_relation_count
    assert sorted_relation_reprs(served) == sorted_relation_reprs(direct)
    assert all(query.largest_in_list <= INSPECTION_IN_LIST_LIMIT for query in warehouse.queries)


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnRequestEquivalenceTestCase(
            description="sparse request keeps exact SHOW COLUMNS reads",
            schemas=("staging", "marts"),
            names=("orders", "customers_v", "transient_events", "revenue"),
            expected_query_kinds=("show_columns",) * 4,
        ),
        ColumnRequestEquivalenceTestCase(
            description="broad request reads each schema's columns once without IN lists",
            schemas=("staging",),
            names=None,
            expected_query_kinds=("columns",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_reading_columns_through_catalog_then_matches_direct_adapter(
    test_case: ColumnRequestEquivalenceTestCase,
) -> None:
    adapter, connection, warehouse = build_offline_snowflake(
        relations=build_inspection_catalog_relations()
    )
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database="analytics",
        schemas=test_case.schemas,
        names=test_case.names,
    )
    direct: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(connection=connection, relations=relations)
    )
    warehouse.reset()
    catalog: InspectionCatalog = InspectionCatalog(adapter=adapter, connection=connection)

    served: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        catalog.get_columns_for_relations(relations=relations)
    )
    repeated: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        catalog.get_columns_for_relations(relations=relations)
    )

    assert served == direct
    assert repeated == direct
    assert Counter(query.kind for query in warehouse.queries) == Counter(
        test_case.expected_query_kinds
    )
    assert all(query.largest_in_list == 0 for query in warehouse.queries)


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessReuseTestCase(
            description="freshness reuses listings without another table read",
            requests=(
                ("analytics", "staging", "orders"),
                ("analytics", "staging", "transient_events"),
                ("analytics", "marts", "revenue"),
            ),
            listed_schemas=("staging", "marts"),
            expected_metadata_reads=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_open_catalog_when_reading_source_freshness_then_reuses_schema_listing(
    test_case: FreshnessReuseTestCase,
) -> None:
    adapter, connection, warehouse = build_offline_snowflake(
        relations=build_inspection_catalog_relations()
    )
    requests: tuple[TableFreshnessRequest, ...] = tuple(
        TableFreshnessRequest(database=database, schema=schema, name=name)
        for database, schema, name in test_case.requests
    )
    direct: dict[TableFreshnessRequest, TableFreshnessMetadata] = (
        adapter.get_tables_freshness_metadata(connection=connection, requests=requests)
    )
    warehouse.reset()

    with open_inspection_catalog(adapter=adapter, connection=connection) as catalog:
        _ = catalog.list_relations(database="analytics", schemas=test_case.listed_schemas)
        served: dict[TableFreshnessRequest, TableFreshnessMetadata] = (
            adapter.get_tables_freshness_metadata(connection=connection, requests=requests)
        )

    assert served == direct
    assert len(warehouse.queries) == test_case.expected_metadata_reads


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessErrorTestCase(
            description="view freshness fails like the direct read",
            request=("analytics", "staging", "customers_v"),
            expected_error_fragment="only supports physical tables",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_open_catalog_when_freshness_targets_a_view_then_raises_like_direct_read(
    test_case: FreshnessErrorTestCase,
) -> None:
    adapter, connection, _ = build_offline_snowflake(relations=build_inspection_catalog_relations())
    database, schema, name = test_case.request
    requests: tuple[TableFreshnessRequest, ...] = (
        TableFreshnessRequest(database=database, schema=schema, name=name),
    )
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        _ = adapter.get_tables_freshness_metadata(connection=connection, requests=requests)

    with (
        open_inspection_catalog(adapter=adapter, connection=connection),
        pytest.raises(AdapterUserError, match=test_case.expected_error_fragment),
    ):
        _ = adapter.get_tables_freshness_metadata(connection=connection, requests=requests)


@pytest.mark.parametrize(
    "test_case",
    [
        RepeatedLookupTestCase(
            description="state table, model, and whole-schema lookups share one listing",
            lookups=(("_sqlbuild_fingerprints",), ("orders",), None),
            expected_relation_counts=(0, 1, 47),
            expected_query_kinds=("tables",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_lookups_when_catalog_is_open_then_lists_schema_once(
    test_case: RepeatedLookupTestCase,
) -> None:
    adapter, connection, warehouse = build_offline_snowflake(
        relations=build_inspection_catalog_relations()
    )
    catalog: InspectionCatalog = InspectionCatalog(adapter=adapter, connection=connection)

    counts: tuple[int, ...] = tuple(
        len(catalog.list_relations(database="analytics", schemas=("staging",), names=names))
        for names in test_case.lookups
    )

    assert counts == test_case.expected_relation_counts
    assert tuple(query.kind for query in warehouse.queries) == test_case.expected_query_kinds


@pytest.mark.parametrize(
    "test_case",
    [
        SpeculativePrefetchTestCase(
            description="unreadable speculative schema fails only the request that needs it",
            failing_schema="RESTRICTED",
            expected_error_fragment="not authorized",
            expected_failed_reads=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unreadable_schema_when_prefetching_best_effort_then_only_real_reads_fail(
    test_case: SpeculativePrefetchTestCase,
) -> None:
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=build_inspection_catalog_relations(),
        failing_metadata_schemas=frozenset({test_case.failing_schema}),
    )
    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(warehouse=warehouse)
    catalog: InspectionCatalog = InspectionCatalog(adapter=adapter, connection=adapter.connect({}))

    catalog.prefetch_schema_listings(
        scopes=(("analytics", "staging"), ("analytics", test_case.failing_schema.lower())),
        best_effort=True,
    )
    staging: tuple[RelationInfo, ...] = catalog.list_relations(
        database="analytics", schemas=("staging",), names=("orders",)
    )
    with pytest.raises(RuntimeError, match=test_case.expected_error_fragment):
        _ = catalog.list_relations(
            database="analytics", schemas=(test_case.failing_schema.lower(),)
        )

    assert len(staging) == 1
    assert len(warehouse.queries_of_kind("tables")) == 1
    assert len(warehouse.attempted_sql) - len(warehouse.queries) == test_case.expected_failed_reads


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
