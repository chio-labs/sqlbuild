from __future__ import annotations

import pytest

from sqlbuild.compiler.node_source_watermarks.main.classify_staleness import (
    classify_node_source_watermark_staleness,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkStaleness,
    SourceWatermarkEntry,
    WatermarkFrontierMember,
    WatermarkGraphKey,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkStalenessStatus
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    NodeSourceWatermarkStalenessClassifierTestCase,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    graph_key,
    model_node,
    nodes_by_key,
    source_entry,
    source_node,
    source_record,
    unknown_source_entry,
    watermark_record,
)

SOURCE_KEY: WatermarkGraphKey = graph_key("raw.events", node_type="source")
ROOT_KEY: WatermarkGraphKey = graph_key("fact_orders")
TABLE_KEY: WatermarkGraphKey = graph_key("stg_orders")
ROOT_IDENTITY: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type="model",
    node_name="fact_orders",
)
TABLE_IDENTITY: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type="model",
    node_name="stg_orders",
)
EVENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.events",
    target_database=None,
    target_schema="main",
    target_name="events",
)
CURRENT_RECORD: SourceFreshnessRecord = source_record(
    EVENTS, data_version="2", data_hash="hash-2", value_kind="integer"
)
OLD_ENTRY: SourceWatermarkEntry = source_entry(
    EVENTS, data_version="1", data_hash="hash-1", value_kind="integer"
)
CURRENT_ENTRY: SourceWatermarkEntry = source_entry(
    EVENTS, data_version="2", data_hash="hash-2", value_kind="integer"
)
DIRECT_FRONTIER: WatermarkFrontierMember = WatermarkFrontierMember(
    root_key=ROOT_KEY, frontier_key=SOURCE_KEY
)
TABLE_FRONTIER: WatermarkFrontierMember = WatermarkFrontierMember(
    root_key=ROOT_KEY, frontier_key=TABLE_KEY
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkStalenessClassifierTestCase(
            description=(
                "direct source frontier is fresh when selected root watermark matches current source"
            ),
            frontier_members=(DIRECT_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True), source_node("raw.events")
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                ROOT_IDENTITY: watermark_record(ROOT_IDENTITY, sources=(CURRENT_ENTRY,))
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=SOURCE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.FRESH,
                    watermark_entry=CURRENT_ENTRY,
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="direct source frontier is stale when selected root watermark differs",
            frontier_members=(DIRECT_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True), source_node("raw.events")
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                ROOT_IDENTITY: watermark_record(ROOT_IDENTITY, sources=(OLD_ENTRY,))
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=SOURCE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                    watermark_entry=OLD_ENTRY,
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="direct source frontier is unknown when selected root watermark is missing",
            frontier_members=(DIRECT_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True), source_node("raw.events")
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={},
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=SOURCE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.UNKNOWN,
                    reason="missing_frontier_watermark",
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="table frontier is fresh when table watermark matches current source",
            frontier_members=(TABLE_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=True),
                source_node("raw.events"),
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={TABLE_IDENTITY: (EVENTS,)},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                TABLE_IDENTITY: watermark_record(TABLE_IDENTITY, sources=(CURRENT_ENTRY,))
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=TABLE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.FRESH,
                    watermark_entry=CURRENT_ENTRY,
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="table frontier is stale when selected root watermark is behind table",
            frontier_members=(TABLE_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=True),
                source_node("raw.events"),
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={TABLE_IDENTITY: (EVENTS,)},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                ROOT_IDENTITY: watermark_record(ROOT_IDENTITY, sources=(OLD_ENTRY,)),
                TABLE_IDENTITY: watermark_record(TABLE_IDENTITY, sources=(CURRENT_ENTRY,)),
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=TABLE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                    watermark_entry=OLD_ENTRY,
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="table frontier is stale when table watermark is behind current source",
            frontier_members=(TABLE_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=True),
                source_node("raw.events"),
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={TABLE_IDENTITY: (EVENTS,)},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                TABLE_IDENTITY: watermark_record(TABLE_IDENTITY, sources=(OLD_ENTRY,))
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=TABLE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                    watermark_entry=OLD_ENTRY,
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="table frontier preserves unknown source from table watermark payload",
            frontier_members=(TABLE_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=True),
                source_node("raw.events"),
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={TABLE_IDENTITY: (EVENTS,)},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={
                TABLE_IDENTITY: watermark_record(
                    TABLE_IDENTITY,
                    unknown_sources=(
                        unknown_source_entry(EVENTS, reason="missing_upstream_watermark"),
                    ),
                )
            },
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=TABLE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.UNKNOWN,
                    reason="missing_upstream_watermark",
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
        NodeSourceWatermarkStalenessClassifierTestCase(
            description="table frontier is unknown when table watermark record is missing",
            frontier_members=(TABLE_FRONTIER,),
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=True),
                source_node("raw.events"),
            ),
            source_identities_by_key={SOURCE_KEY: EVENTS},
            required_source_identities_by_node={TABLE_IDENTITY: (EVENTS,)},
            current_source_records={EVENTS: CURRENT_RECORD},
            watermark_records={},
            expected_classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_KEY,
                    frontier_key=TABLE_KEY,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.UNKNOWN,
                    reason="missing_frontier_watermark",
                    current_record=CURRENT_RECORD,
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_frontier_watermarks_when_classifying_then_returns_fresh_stale_or_unknown(
    test_case: NodeSourceWatermarkStalenessClassifierTestCase,
) -> None:
    result: tuple[NodeSourceWatermarkStaleness, ...] = classify_node_source_watermark_staleness(
        frontier_members=test_case.frontier_members,
        nodes=test_case.nodes,
        source_identities_by_key=test_case.source_identities_by_key,
        required_source_identities_by_node=test_case.required_source_identities_by_node,
        current_source_records=test_case.current_source_records,
        watermark_records=test_case.watermark_records,
    )

    assert result == test_case.expected_classifications
