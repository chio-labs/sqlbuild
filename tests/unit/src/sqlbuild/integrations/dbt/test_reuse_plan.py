from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtInteropPlan,
    DbtModelPlanningResult,
    DbtReuseFromCompileResult,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers import reuse_plan
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_plan import (
    build_dbt_dependency_baseline_plan_output,
    build_dbt_reuse_plan_output,
)
from sqlbuild.integrations.dbt.types import (
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReusePlanReason,
)
from sqlbuild.spec.models.project import DbtConfig, DbtReuseFromConfig, LocalConfig, ProjectConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtReuseOriginRelationTestCase,
    DbtReusePlanOutputTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    FakeReusePlanAdapter,
    assert_reuse_plan_output_matches,
    build_dbt_interop_plan_for_reuse_scope,
    build_dbt_model_plan_entry,
    build_manifest_data,
    build_reuse_plan_current_manifest_nodes,
    build_reuse_plan_origin_key_current_manifest_nodes,
    build_reuse_plan_origin_key_reuse_manifest_nodes,
    build_reuse_plan_reuse_manifest_nodes,
    reuse_plan_rebuild_reasons,
)

REUSE_PLAN_OUTPUT_TEST_CASES: tuple[DbtReusePlanOutputTestCase, ...] = (
    DbtReusePlanOutputTestCase(
        description="returns none when reuse_from is not configured",
        configure_reuse_from=False,
        include_model_plan=True,
        expected_is_none=True,
        expected_complete_reuse_unique_ids=(),
        expected_seeded_reuse_unique_ids=(),
    ),
    DbtReusePlanOutputTestCase(
        description="returns none before dbt model plan is available",
        configure_reuse_from=True,
        include_model_plan=False,
        expected_is_none=True,
        expected_complete_reuse_unique_ids=(),
        expected_seeded_reuse_unique_ids=(),
    ),
    DbtReusePlanOutputTestCase(
        description="builds reuse plan from compiled reuse manifest and model plan",
        configure_reuse_from=True,
        include_model_plan=True,
        expected_is_none=False,
        expected_complete_reuse_unique_ids=("model.analytics.orders",),
        expected_seeded_reuse_unique_ids=("model.analytics.events",),
    ),
)

REUSE_ORIGIN_RELATION_TEST_CASES: tuple[DbtReuseOriginRelationTestCase, ...] = (
    DbtReuseOriginRelationTestCase(
        description="matches origin relations by database schema and alias with partial misses",
        existing_relations=(
            ("warehouse", "prod_marts", "orders_prod"),
            ("lakehouse", "prod_marts", "payments_prod"),
        ),
        expected_complete_reuse_unique_ids=(
            "model.analytics.orders",
            "model.analytics.payments",
        ),
        expected_rebuild_unique_ids=("model.analytics.customers",),
        expected_rebuild_reasons=(DbtReusePlanReason.ORIGIN_RELATION_MISSING,),
        expected_list_relation_calls=(
            (
                "warehouse",
                ("prod_marts", "prod_core"),
                ("orders_prod", "customers_prod"),
            ),
            ("lakehouse", ("prod_marts",), ("payments_prod",)),
        ),
    ),
    DbtReuseOriginRelationTestCase(
        description="matches all origin relations across databases and schemas",
        existing_relations=(
            ("warehouse", "prod_marts", "orders_prod"),
            ("warehouse", "prod_core", "customers_prod"),
            ("lakehouse", "prod_marts", "payments_prod"),
        ),
        expected_complete_reuse_unique_ids=(
            "model.analytics.orders",
            "model.analytics.customers",
            "model.analytics.payments",
        ),
        expected_rebuild_unique_ids=(),
        expected_rebuild_reasons=(),
        expected_list_relation_calls=(
            (
                "warehouse",
                ("prod_marts", "prod_core"),
                ("orders_prod", "customers_prod"),
            ),
            ("lakehouse", ("prod_marts",), ("payments_prod",)),
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    REUSE_PLAN_OUTPUT_TEST_CASES,
    ids=[case.description for case in REUSE_PLAN_OUTPUT_TEST_CASES],
)
def test_given_reuse_from_pipeline_inputs_when_building_reuse_plan_then_returns_expected_plan(
    test_case: DbtReusePlanOutputTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=build_reuse_plan_current_manifest_nodes())
    )
    plan: DbtInteropPlan = build_dbt_interop_plan_for_reuse_scope(
        dbt_selected_unique_ids=("model.analytics.orders", "model.analytics.events")
    )
    dbt_model_plan: DbtModelPlanningResult | None = (
        DbtModelPlanningResult(
            entries=(
                build_dbt_model_plan_entry(
                    unique_id="model.analytics.orders",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.RELATION_MISSING,
                ),
                build_dbt_model_plan_entry(
                    unique_id="model.analytics.events",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.CHECKSUM_CHANGED,
                ),
            )
        )
        if test_case.include_model_plan
        else None
    )

    def fake_compile_reuse_from_manifest(**kwargs: object) -> DbtReuseFromCompileResult:
        del kwargs
        return DbtReuseFromCompileResult(
            git_ref="prod",
            manifest_contents=json.dumps(
                build_manifest_data(nodes=build_reuse_plan_reuse_manifest_nodes())
            ),
            command=DbtCommandResult(argv=("dbt", "compile"), returncode=0),
        )

    monkeypatch.setattr(
        reuse_plan,
        "compile_reuse_from_manifest",
        fake_compile_reuse_from_manifest,
    )

    result: DbtReusePlanningResult | None = build_dbt_reuse_plan_output(
        project_dir=tmp_path,
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                dbt=DbtConfig(
                    reuse_from=(
                        DbtReuseFromConfig(
                            git_ref="prod",
                            generate_schema_name_override="dbt/macros/prod.sql",
                        )
                        if test_case.configure_reuse_from
                        else DbtReuseFromConfig()
                    )
                ),
            ),
            local_config=LocalConfig(),
        ),
        current_manifest=current_manifest,
        adapter=FakeReusePlanAdapter(
            relations=(
                RelationInfo(
                    database=None,
                    schema=None,
                    name="orders",
                    relation_type="BASE TABLE",
                ),
                RelationInfo(
                    database=None,
                    schema=None,
                    name="events",
                    relation_type="BASE TABLE",
                ),
            )
        ),
        adapter_name="duckdb",
        dbt_model_plan=dbt_model_plan,
        plan=plan,
        dbt_options=DbtCliOptions(project_dir=tmp_path / "dbt"),
        runner=DbtRunner(),
    )

    assert_reuse_plan_output_matches(
        result=result,
        expected_is_none=test_case.expected_is_none,
        expected_complete_reuse_unique_ids=test_case.expected_complete_reuse_unique_ids,
        expected_seeded_reuse_unique_ids=test_case.expected_seeded_reuse_unique_ids,
    )


@pytest.mark.parametrize(
    "test_case",
    REUSE_ORIGIN_RELATION_TEST_CASES,
    ids=[case.description for case in REUSE_ORIGIN_RELATION_TEST_CASES],
)
def test_given_origin_relation_keys_when_building_reuse_plan_then_marks_missing_relations(
    test_case: DbtReuseOriginRelationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=build_reuse_plan_origin_key_current_manifest_nodes())
    )
    plan: DbtInteropPlan = build_dbt_interop_plan_for_reuse_scope(
        dbt_selected_unique_ids=(
            "model.analytics.orders",
            "model.analytics.customers",
            "model.analytics.payments",
        )
    )
    dbt_model_plan: DbtModelPlanningResult = DbtModelPlanningResult(
        entries=(
            build_dbt_model_plan_entry(
                unique_id="model.analytics.orders",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
            build_dbt_model_plan_entry(
                unique_id="model.analytics.customers",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
            build_dbt_model_plan_entry(
                unique_id="model.analytics.payments",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
        )
    )
    adapter: FakeReusePlanAdapter = FakeReusePlanAdapter(
        relations=tuple(
            RelationInfo(database=database, schema=schema, name=name, relation_type="BASE TABLE")
            for database, schema, name in test_case.existing_relations
        )
    )

    def fake_compile_reuse_from_manifest(**kwargs: object) -> DbtReuseFromCompileResult:
        del kwargs
        return DbtReuseFromCompileResult(
            git_ref="prod",
            manifest_contents=json.dumps(
                build_manifest_data(nodes=build_reuse_plan_origin_key_reuse_manifest_nodes())
            ),
            command=DbtCommandResult(argv=("dbt", "compile"), returncode=0),
        )

    monkeypatch.setattr(
        reuse_plan,
        "compile_reuse_from_manifest",
        fake_compile_reuse_from_manifest,
    )

    result: DbtReusePlanningResult | None = build_dbt_reuse_plan_output(
        project_dir=tmp_path,
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                dbt=DbtConfig(
                    reuse_from=DbtReuseFromConfig(
                        git_ref="prod",
                        generate_schema_name_override="dbt/macros/prod.sql",
                    )
                ),
            ),
            local_config=LocalConfig(),
        ),
        current_manifest=current_manifest,
        adapter=adapter,
        adapter_name="duckdb",
        dbt_model_plan=dbt_model_plan,
        plan=plan,
        dbt_options=DbtCliOptions(project_dir=tmp_path / "dbt"),
        runner=DbtRunner(),
    )

    assert result is not None
    assert result.complete_reuse_unique_ids == test_case.expected_complete_reuse_unique_ids
    assert result.rebuild_unique_ids == test_case.expected_rebuild_unique_ids
    assert reuse_plan_rebuild_reasons(result) == test_case.expected_rebuild_reasons
    assert tuple(adapter.list_relation_calls) == test_case.expected_list_relation_calls


@pytest.mark.parametrize(
    "test_case",
    REUSE_ORIGIN_RELATION_TEST_CASES,
    ids=[case.description for case in REUSE_ORIGIN_RELATION_TEST_CASES],
)
def test_given_missing_origin_relation_when_building_dependency_baseline_then_rebuilds_candidate(
    test_case: DbtReuseOriginRelationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=build_reuse_plan_origin_key_current_manifest_nodes())
    )
    dbt_model_plan: DbtModelPlanningResult = DbtModelPlanningResult(
        entries=(
            build_dbt_model_plan_entry(
                unique_id="model.analytics.orders",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
            build_dbt_model_plan_entry(
                unique_id="model.analytics.customers",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
            build_dbt_model_plan_entry(
                unique_id="model.analytics.payments",
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.RELATION_MISSING,
            ),
        )
    )
    adapter: FakeReusePlanAdapter = FakeReusePlanAdapter(
        relations=tuple(
            RelationInfo(database=database, schema=schema, name=name, relation_type="BASE TABLE")
            for database, schema, name in test_case.existing_relations
        )
    )

    def fake_compile_reuse_from_manifest(**kwargs: object) -> DbtReuseFromCompileResult:
        del kwargs
        return DbtReuseFromCompileResult(
            git_ref="prod",
            manifest_contents=json.dumps(
                build_manifest_data(nodes=build_reuse_plan_origin_key_reuse_manifest_nodes())
            ),
            command=DbtCommandResult(argv=("dbt", "compile"), returncode=0),
        )

    monkeypatch.setattr(
        reuse_plan,
        "compile_reuse_from_manifest",
        fake_compile_reuse_from_manifest,
    )

    result: DbtReusePlanningResult | None = build_dbt_dependency_baseline_plan_output(
        project_dir=tmp_path,
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                dbt=DbtConfig(
                    reuse_from=DbtReuseFromConfig(
                        git_ref="prod",
                        generate_schema_name_override="dbt/macros/prod.sql",
                    )
                ),
            ),
            local_config=LocalConfig(),
        ),
        current_manifest=current_manifest,
        adapter=adapter,
        adapter_name="duckdb",
        dbt_model_plan=dbt_model_plan,
        scoped_unique_ids=(
            "model.analytics.orders",
            "model.analytics.customers",
            "model.analytics.payments",
        ),
        dbt_options=DbtCliOptions(project_dir=tmp_path / "dbt"),
        runner=DbtRunner(),
    )

    assert result is not None
    assert result.complete_reuse_unique_ids == test_case.expected_complete_reuse_unique_ids
    assert result.rebuild_unique_ids == test_case.expected_rebuild_unique_ids
    assert reuse_plan_rebuild_reasons(result) == test_case.expected_rebuild_reasons
    assert tuple(adapter.list_relation_calls) == test_case.expected_list_relation_calls
