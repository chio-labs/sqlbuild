from __future__ import annotations

import pytest

from sqlbuild.compiler.node_source_watermarks.main.native_graph import (
    build_native_node_source_watermark_inputs,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NativeNodeSourceWatermarkInputs,
    NodeSourceWatermarkIdentity,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    NativeNodeSourceWatermarkInputsTestCase,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    compiled_model_key,
    compiled_source_key,
    model_plan_entry,
    node_watermark_identity,
)

FACT: NodeSourceWatermarkIdentity = node_watermark_identity("fact_orders")
DIM: NodeSourceWatermarkIdentity = node_watermark_identity("dim_customers")
EVENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.events",
    target_database=None,
    target_schema="main",
    target_name="raw_events",
)
CUSTOMERS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.customers",
    target_database=None,
    target_schema="main",
    target_name="raw_customers",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeNodeSourceWatermarkInputsTestCase(
            description="passes through views and maps materialized upstream table frontier",
            expected_inputs=NativeNodeSourceWatermarkInputs(
                source_identities_by_node={
                    FACT: (CUSTOMERS, EVENTS),
                    DIM: (CUSTOMERS,),
                },
                direct_source_identities_by_node={
                    FACT: (EVENTS,),
                    DIM: (CUSTOMERS,),
                },
                upstream_node_identities_by_node={FACT: (DIM,)},
            ),
        )
    ],
    ids=["passes through views and maps materialized upstream table frontier"],
)
def test_given_native_plan_when_building_watermark_inputs_then_returns_graph_context(
    test_case: NativeNodeSourceWatermarkInputsTestCase,
) -> None:
    plan: PlanOutput = PlanOutput(
        model_entries=(
            model_plan_entry("fact_orders", materialization_type=MaterializationType.TABLE),
            model_plan_entry("stg_orders", materialization_type=MaterializationType.VIEW),
            model_plan_entry("dim_customers", materialization_type=MaterializationType.TABLE),
        ),
        upstream_deps={
            compiled_model_key("fact_orders"): (
                compiled_model_key("stg_orders"),
                compiled_model_key("dim_customers"),
            ),
            compiled_model_key("stg_orders"): (compiled_source_key("raw.events"),),
            compiled_model_key("dim_customers"): (compiled_source_key("raw.customers"),),
        },
        source_map={
            "raw.events": SourceEntry(name="raw.events", schema="main", table="raw_events"),
            "raw.customers": SourceEntry(
                name="raw.customers",
                schema="main",
                table="raw_customers",
            ),
        },
    )

    result: NativeNodeSourceWatermarkInputs = build_native_node_source_watermark_inputs(plan=plan)

    assert result == test_case.expected_inputs
