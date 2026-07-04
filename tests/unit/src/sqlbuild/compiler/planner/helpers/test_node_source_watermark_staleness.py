from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkIdentity
from sqlbuild.compiler.planner.helpers.pruning.node_source_watermark_staleness import (
    build_node_source_watermark_staleness_warnings,
)
from sqlbuild.compiler.planner.models import PlanWarning
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    source_entry,
    watermark_record,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    NodeSourceWatermarkWarningTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_node_source_watermark_warning_plan,
)

MODEL_A_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="a",
)
MODEL_B_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="b",
)
SOURCE_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SOURCE,
    name="raw_orders",
)
SOURCE_IDENTITY: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw_orders",
    target_database=None,
    target_schema="raw",
    target_name="raw_orders",
)
MODEL_B_IDENTITY: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
    node_type=CompiledResourceType.MODEL.value,
    node_name="b",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkWarningTestCase(
            description="stale materialized frontier emits grouped warning",
            upstream_deps={
                MODEL_A_KEY: (MODEL_B_KEY,),
                MODEL_B_KEY: (SOURCE_KEY,),
            },
            model_names=("a", "b"),
            source_names=("raw_orders",),
            watermark_records={
                MODEL_B_IDENTITY: watermark_record(
                    MODEL_B_IDENTITY,
                    sources=(
                        source_entry(
                            SOURCE_IDENTITY,
                            data_version="2026-06-29T17:00:00+00:00",
                            data_hash="hash-stale",
                        ),
                    ),
                )
            },
            expected_warning_fragments=(
                "Stale inputs detected",
                "Affected selected models:",
                "a",
                "Stale frontier tables:",
                "b",
                "Changed sources:",
                "raw_orders",
            ),
            unexpected_warning_fragments=("Unknown freshness proofs",),
        ),
        NodeSourceWatermarkWarningTestCase(
            description="missing materialized frontier watermark is unknown",
            upstream_deps={
                MODEL_A_KEY: (MODEL_B_KEY,),
                MODEL_B_KEY: (SOURCE_KEY,),
            },
            model_names=("a", "b"),
            source_names=("raw_orders",),
            watermark_records={},
            expected_warning_fragments=(
                "Stale inputs detected",
                "Affected selected models:",
                "a",
                "Unknown freshness proofs:",
                "b (missing_frontier_watermark)",
            ),
            unexpected_warning_fragments=("Stale frontier tables", "Changed sources"),
        ),
        NodeSourceWatermarkWarningTestCase(
            description="direct source frontier does not warn",
            upstream_deps={MODEL_A_KEY: (SOURCE_KEY,)},
            model_names=("a",),
            source_names=("raw_orders",),
            watermark_records={},
            expected_warning_fragments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_plan_when_building_watermark_warnings_then_reports_expected_inputs(
    test_case: NodeSourceWatermarkWarningTestCase,
) -> None:
    warnings: tuple[PlanWarning, ...] = build_node_source_watermark_staleness_warnings(
        plan=build_node_source_watermark_warning_plan(
            upstream_deps=test_case.upstream_deps,
            model_names=test_case.model_names,
            source_names=test_case.source_names,
        ),
        watermark_records=test_case.watermark_records,
    )

    output: str = "\n".join(warning.message for warning in warnings)

    assert len(warnings) == (1 if test_case.expected_warning_fragments else 0)
    for fragment in test_case.expected_warning_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_warning_fragments:
        assert fragment not in output
