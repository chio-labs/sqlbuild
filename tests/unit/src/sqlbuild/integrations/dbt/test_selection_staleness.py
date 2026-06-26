from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    _stale_out_of_selection_warning_messages,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph, DbtModelPlanEntry
from sqlbuild.integrations.dbt.types import DbtModelPlanAction, DbtModelPlanReason
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtSelectionStalenessWarningTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_dbt_selection_staleness_entry,
    build_dbt_selection_staleness_graph,
    build_dbt_selection_staleness_manifest,
)

MODEL_A: str = "model.analytics.a"
MODEL_B: str = "model.analytics.b"
MODEL_C: str = "model.analytics.c"
MODEL_D: str = "model.analytics.d"
MODEL_E: str = "model.analytics.e"
SEED_ORDERS: str = "seed.analytics.raw_orders"
SEED_CUSTOMERS: str = "seed.analytics.raw_customers"
SOURCE_ORDERS: str = "source.analytics.raw.orders"

TEST_CASES: tuple[DbtSelectionStalenessWarningTestCase, ...] = (
    DbtSelectionStalenessWarningTestCase(
        description="direct changed model parent outside selection warns",
        upstream_deps={MODEL_C: (MODEL_B,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(MODEL_B,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- b"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="direct changed model parent in run set does not warn",
        upstream_deps={MODEL_C: (MODEL_B,)},
        selected_unique_ids=(MODEL_B, MODEL_C),
        run_unique_ids=(MODEL_B, MODEL_C),
        changed_model_unique_ids=(MODEL_B,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=0,
        expected_warning_fragments=(),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="multi-hop changed model root outside selection warns",
        upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(MODEL_A,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- a", "- b"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="selected root and leaf still warn for unbuilt intermediate",
        upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
        selected_unique_ids=(MODEL_A, MODEL_C),
        run_unique_ids=(MODEL_A, MODEL_C),
        changed_model_unique_ids=(MODEL_A,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- b"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="mixed selected and unselected changed parents warns only for unselected",
        upstream_deps={MODEL_C: (MODEL_A, MODEL_B)},
        selected_unique_ids=(MODEL_A, MODEL_C),
        run_unique_ids=(MODEL_A, MODEL_C),
        changed_model_unique_ids=(MODEL_A, MODEL_B),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- b"),
        unexpected_warning_fragments=("- a",),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="changed seed outside selection warns with seed compatibility text",
        upstream_deps={MODEL_C: (SEED_ORDERS,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(),
        changed_seed_unique_ids=(SEED_ORDERS,),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=(
            "selected dbt model 'c' will build on",
            "- raw_orders",
        ),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="changed seed in selected run set does not warn",
        upstream_deps={MODEL_C: (SEED_ORDERS,)},
        selected_unique_ids=(SEED_ORDERS, MODEL_C),
        run_unique_ids=(MODEL_C,),
        changed_model_unique_ids=(),
        changed_seed_unique_ids=(SEED_ORDERS,),
        changed_source_unique_ids=(),
        expected_warning_count=0,
        expected_warning_fragments=(),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="changed source outside selection warns",
        upstream_deps={MODEL_C: (SOURCE_ORDERS,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(SOURCE_ORDERS,),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- orders"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="multi-hop changed seed outside selection warns",
        upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (SEED_ORDERS,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(),
        changed_seed_unique_ids=(SEED_ORDERS,),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=(
            "selected dbt model 'c' will build on",
            "- raw_orders",
        ),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="multi-hop changed source outside selection warns",
        upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (SOURCE_ORDERS,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(SOURCE_ORDERS,),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- b", "- orders"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="selected model can run and still warn for unselected upstream",
        upstream_deps={MODEL_C: (MODEL_B,)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(MODEL_C,),
        changed_model_unique_ids=(MODEL_B, MODEL_C),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- b"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="diamond graph reports both stale intermediates",
        upstream_deps={MODEL_E: (MODEL_C, MODEL_D), MODEL_C: (MODEL_B,), MODEL_D: (MODEL_B,)},
        selected_unique_ids=(MODEL_E,),
        run_unique_ids=(),
        changed_model_unique_ids=(MODEL_B,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'e' will build on", "- c", "- d"),
    ),
    DbtSelectionStalenessWarningTestCase(
        description="self cycle does not report selected model as its own trigger",
        upstream_deps={MODEL_C: (MODEL_C, MODEL_A)},
        selected_unique_ids=(MODEL_C,),
        run_unique_ids=(),
        changed_model_unique_ids=(MODEL_A,),
        changed_seed_unique_ids=(),
        changed_source_unique_ids=(),
        expected_warning_count=1,
        expected_warning_fragments=("selected dbt model 'c' will build on", "- a"),
        unexpected_warning_fragments=("- c",),
    ),
)


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_dbt_graph_when_classifying_selection_staleness_then_warns_for_stale_upstreams(
    test_case: DbtSelectionStalenessWarningTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_selection_staleness_manifest(
        model_unique_ids=(MODEL_A, MODEL_B, MODEL_C, MODEL_D, MODEL_E),
        seed_unique_ids=(SEED_ORDERS, SEED_CUSTOMERS),
        source_unique_ids=(SOURCE_ORDERS,),
    )
    graph: DbtCombinedGraph = build_dbt_selection_staleness_graph(
        upstream_deps=test_case.upstream_deps
    )
    entries_by_unique_id: dict[str, DbtModelPlanEntry] = {
        unique_id: build_dbt_selection_staleness_entry(
            unique_id=unique_id,
            action=(
                DbtModelPlanAction.RUN
                if unique_id in set(test_case.run_unique_ids)
                or unique_id in set(test_case.changed_model_unique_ids)
                else DbtModelPlanAction.CURRENT
            ),
            reason=(
                DbtModelPlanReason.CHECKSUM_CHANGED
                if unique_id in set(test_case.changed_model_unique_ids)
                else DbtModelPlanReason.NO_CHANGE
            ),
        )
        for unique_id in (MODEL_A, MODEL_B, MODEL_C, MODEL_D, MODEL_E)
    }

    warnings: tuple[str, ...] = _stale_out_of_selection_warning_messages(
        manifest=manifest,
        graph=graph,
        selected_unique_ids=frozenset(test_case.selected_unique_ids),
        entries_by_unique_id=entries_by_unique_id,
        changed_seed_unique_ids=frozenset(test_case.changed_seed_unique_ids),
        changed_source_unique_ids=frozenset(test_case.changed_source_unique_ids),
    )

    rendered_warnings: str = "\n".join(warnings)
    assert len(warnings) == test_case.expected_warning_count
    for fragment in test_case.expected_warning_fragments:
        assert fragment in rendered_warnings
    for fragment in test_case.unexpected_warning_fragments:
        assert fragment not in rendered_warnings
