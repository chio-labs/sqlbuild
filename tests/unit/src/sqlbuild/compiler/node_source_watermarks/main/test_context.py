from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.node_source_watermarks.main._build_payload import (
    build_node_source_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.main.context import (
    build_node_source_watermark_execution_context,
)
from sqlbuild.compiler.node_source_watermarks.main.record_successful import (
    record_successful_node_source_watermark,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkPayload,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
    NodeSourceWatermarkTarget,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    NodeSourceWatermarkExecutionContextTestCase,
    NodeSourceWatermarkPayloadBuildTestCase,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    complete_for_result,
    expected_buffered_record_count,
    record_upstream_context_if_required,
    source_entry,
    source_hashes_for_result,
    source_record,
    unknown_reasons_for_result,
)

EVENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.events",
    target_database=None,
    target_schema="main",
    target_name="dev",
)
PAYMENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.payments",
    target_database=None,
    target_schema="main",
    target_name="dev",
)
MODEL_A: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type="model",
    node_name="a",
)
MODEL_B: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type="model",
    node_name="b",
)
MODEL_C: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type="model",
    node_name="c",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkPayloadBuildTestCase(
            description="records direct current source freshness as direct watermark",
            required_source_identities=(EVENTS,),
            direct_source_records={
                EVENTS: source_record(EVENTS, data_version="2026-06-29T15:37:00", data_hash="evt-2")
            },
            inherited_payloads=(),
            expected_complete=True,
            expected_source_hashes=("evt-2",),
            expected_source_kinds=("direct",),
            expected_unknown_reasons=(),
        ),
        NodeSourceWatermarkPayloadBuildTestCase(
            description="marks inherited upstream source watermarks as inherited",
            required_source_identities=(EVENTS,),
            direct_source_records={},
            inherited_payloads=(
                NodeSourceWatermarkPayload(
                    version=1,
                    complete=True,
                    sources=(
                        source_entry(
                            EVENTS,
                            data_version="2026-06-29T15:00:00",
                            data_hash="evt-1",
                        ),
                    ),
                ),
            ),
            expected_complete=True,
            expected_source_hashes=("evt-1",),
            expected_source_kinds=("inherited",),
            expected_unknown_reasons=(),
        ),
        NodeSourceWatermarkPayloadBuildTestCase(
            description="marks required source missing from direct and inherited facts as unknown",
            required_source_identities=(EVENTS, PAYMENTS),
            direct_source_records={
                EVENTS: source_record(EVENTS, data_version="2026-06-29T15:37:00", data_hash="evt-2")
            },
            inherited_payloads=(),
            expected_complete=False,
            expected_source_hashes=("evt-2",),
            expected_source_kinds=("direct",),
            expected_unknown_reasons=("missing_upstream_watermark",),
        ),
        NodeSourceWatermarkPayloadBuildTestCase(
            description="keeps oldest timestamp version across multiple inherited inputs",
            required_source_identities=(EVENTS,),
            direct_source_records={},
            inherited_payloads=(
                NodeSourceWatermarkPayload(
                    version=1,
                    complete=True,
                    sources=(
                        source_entry(
                            EVENTS,
                            data_version="2026-06-29T15:40:00",
                            data_hash="evt-2",
                        ),
                    ),
                ),
                NodeSourceWatermarkPayload(
                    version=1,
                    complete=True,
                    sources=(
                        source_entry(
                            EVENTS,
                            data_version="2026-06-29T15:00:00",
                            data_hash="evt-1",
                        ),
                    ),
                ),
            ),
            expected_complete=True,
            expected_source_hashes=("evt-1",),
            expected_source_kinds=("inherited",),
            expected_unknown_reasons=(),
        ),
        NodeSourceWatermarkPayloadBuildTestCase(
            description="marks mixed non-orderable versions as unknown",
            required_source_identities=(EVENTS,),
            direct_source_records={},
            inherited_payloads=(
                NodeSourceWatermarkPayload(
                    version=1,
                    complete=True,
                    sources=(
                        source_entry(
                            EVENTS,
                            value_kind="string",
                            data_version="snapshot-a",
                            data_hash="hash-a",
                        ),
                    ),
                ),
                NodeSourceWatermarkPayload(
                    version=1,
                    complete=True,
                    sources=(
                        source_entry(
                            EVENTS,
                            value_kind="string",
                            data_version="snapshot-b",
                            data_hash="hash-b",
                        ),
                    ),
                ),
            ),
            expected_complete=False,
            expected_source_hashes=(),
            expected_source_kinds=(),
            expected_unknown_reasons=("mixed_non_orderable_watermark",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_watermark_facts_when_building_payload_then_merges_conservatively(
    test_case: NodeSourceWatermarkPayloadBuildTestCase,
) -> None:
    result: NodeSourceWatermarkPayload = build_node_source_watermark_payload(
        required_source_identities=test_case.required_source_identities,
        direct_source_records=test_case.direct_source_records,
        inherited_payloads=test_case.inherited_payloads,
    )

    assert result.complete is test_case.expected_complete
    assert (
        tuple(entry.data_version_hash for entry in result.sources)
        == test_case.expected_source_hashes
    )
    assert (
        tuple(entry.watermark_kind for entry in result.sources) == test_case.expected_source_kinds
    )
    assert (
        tuple(entry.reason for entry in result.unknown_sources)
        == test_case.expected_unknown_reasons
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkExecutionContextTestCase(
            description="buffers direct source watermark record and updates cache",
            node_identity=MODEL_A,
            source_identities_by_node={MODEL_A: (EVENTS,)},
            direct_source_identities_by_node={MODEL_A: (EVENTS,)},
            upstream_node_identities_by_node={},
            expected_record_written=True,
            expected_complete=True,
            expected_source_hashes=("evt-2",),
            expected_unknown_reasons=(),
        ),
        NodeSourceWatermarkExecutionContextTestCase(
            description="inherits same run upstream payload from context cache",
            node_identity=MODEL_B,
            source_identities_by_node={MODEL_A: (EVENTS,), MODEL_B: (EVENTS,)},
            direct_source_identities_by_node={MODEL_A: (EVENTS,)},
            upstream_node_identities_by_node={MODEL_B: (MODEL_A,)},
            expected_record_written=True,
            expected_complete=True,
            expected_source_hashes=("evt-2",),
            expected_unknown_reasons=(),
        ),
        NodeSourceWatermarkExecutionContextTestCase(
            description="does not record nodes without source ancestry",
            node_identity=MODEL_C,
            source_identities_by_node={},
            direct_source_identities_by_node={},
            upstream_node_identities_by_node={},
            expected_record_written=False,
            expected_complete=None,
            expected_source_hashes=(),
            expected_unknown_reasons=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_execution_context_when_node_succeeds_then_buffers_record_and_updates_cache(
    test_case: NodeSourceWatermarkExecutionContextTestCase,
) -> None:
    context: NodeSourceWatermarkExecutionContext = build_node_source_watermark_execution_context(
        latest_watermarks=NodeSourceWatermarkSet(schema="main"),
        direct_source_records={
            EVENTS: source_record(
                EVENTS,
                data_version="2026-06-29T15:37:00",
                data_hash="evt-2",
            )
        },
        direct_source_identities_by_node=test_case.direct_source_identities_by_node,
        source_identities_by_node=test_case.source_identities_by_node,
        upstream_node_identities_by_node=test_case.upstream_node_identities_by_node,
    )
    record_upstream_context_if_required(
        context=context,
        test_case=test_case,
        upstream_identity=MODEL_A,
    )

    result: NodeSourceWatermarkRecord | None = record_successful_node_source_watermark(
        context=context,
        node_identity=test_case.node_identity,
        target=NodeSourceWatermarkTarget(database=None, schema="main", name="target"),
        run_id="run-1",
        node_version_hash="version-target",
        created_at=datetime(2026, 6, 29, 16, 1),
    )

    assert (result is not None) is test_case.expected_record_written
    assert len(context.buffered_records) == expected_buffered_record_count(
        test_case=test_case,
        upstream_identity=MODEL_A,
    )
    assert complete_for_result(result) is test_case.expected_complete
    assert source_hashes_for_result(result) == test_case.expected_source_hashes
    assert unknown_reasons_for_result(result) == test_case.expected_unknown_reasons
