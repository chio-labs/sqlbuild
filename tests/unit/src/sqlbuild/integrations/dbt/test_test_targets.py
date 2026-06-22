from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.compile.models.sql_tests import CompiledModelSqlTestPayload
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.selection.sql_test_targets import (
    adapt_project_for_dbt_sql_tests,
    resolve_dbt_sql_test_target_names,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtSqlTestFixtureNameTestCase,
    DbtSqlTestMultipleBoundaryTestCase,
    DbtSqlTestTargetErrorTestCase,
    DbtSqlTestTargetTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_dbt_sql_test_target_error_manifest,
    build_dbt_sql_test_target_error_project,
    build_dbt_sql_test_target_success_manifest,
    build_project_with_expected_sql_test_targets,
    build_project_with_multiple_dbt_sql_test_boundaries,
    resolve_dbt_sql_test_fixture_names,
)

TEST_TARGET_TEST_CASES: list[DbtSqlTestTargetTestCase] = [
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from compiled SQL",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=(
            'from __dbt_ref("stg_orders")',
            "where amount_cents > 0",
        ),
        expected_absent_fragments=("{{ ref('stg_orders') }}",),
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts qualified dbt expected target",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("analytics.fact_orders",),
        expected_target_names=("analytics__fact_orders",),
        expected_model_names=("analytics__fact_orders",),
        expected_query_fragments=('__dbt_ref("stg_orders")',),
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from unquoted relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("stg_orders")',),
        manifest_kind="unquoted",
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from three-part relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("stg_orders")',),
        manifest_kind="three_part",
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from aliased relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("stg_orders")',),
        manifest_kind="alias",
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites relation only in code, preserving strings and comments",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=(
            'from __dbt_ref("stg_orders") where amount_cents > 0',
            "-- upstream analytics.stg_orders",
            "'analytics.stg_orders' as src",
        ),
        expected_absent_fragments=(
            "-- upstream __dbt_ref",
            "'__dbt_ref",
        ),
        manifest_kind="relation_in_string_and_comment",
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from selected test node shape",
        selected_dbt_unique_ids=("test.analytics.not_null_fact_orders_order_id",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('__dbt_ref("stg_orders")',),
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt source dependency to source fixture",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __source("raw__orders")',),
        manifest_kind="source_dependency",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt source dependency from unquoted relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __source("raw__orders")',),
        manifest_kind="source_unquoted",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt source dependency from three-part relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __source("raw__orders")',),
        manifest_kind="source_three_part",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt source dependency from aliased relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __source("raw__orders")',),
        manifest_kind="source_alias",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites ambiguous dbt source dependency to qualified fixture",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __source("analytics__raw__orders")',),
        manifest_kind="source_ambiguous_fixture",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt seed dependency to seed fixture",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __seed("countries")',),
        manifest_kind="seed_dependency",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt seed dependency from unquoted relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __seed("countries")',),
        manifest_kind="seed_unquoted",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt seed dependency from three-part relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __seed("countries")',),
        manifest_kind="seed_three_part",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites dbt seed dependency from aliased relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __seed("countries")',),
        manifest_kind="seed_alias",
    ),
    DbtSqlTestTargetTestCase(
        description="rewrites ambiguous dbt seed dependency to qualified fixture",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __seed("analytics__countries")',),
        manifest_kind="seed_ambiguous_fixture",
    ),
    DbtSqlTestTargetTestCase(
        description="adapts dbt model chain through source dependency",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_adapted_model_names=("fact_orders", "stg_orders"),
        expected_query_fragments=('from __ref("stg_orders")',),
        manifest_kind="chain_source_dependency",
    ),
    DbtSqlTestTargetTestCase(
        description="adapts dbt model chain through seed dependency",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_adapted_model_names=("fact_orders", "stg_orders"),
        expected_query_fragments=('from __ref("stg_orders")',),
        manifest_kind="chain_seed_dependency",
    ),
    DbtSqlTestTargetTestCase(
        description="preserves explicit dbt ref mock boundary in dbt model chain",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('__dbt_ref("stg_orders")',),
        manifest_kind="chain_source_dependency",
        mock_model_names=("stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="allows mocked dbt snapshot boundary in dbt model chain",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('__dbt_ref("analytics", "stg_orders")',),
        manifest_kind="chain_snapshot_boundary",
        mock_model_names=("analytics__stg_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="allows mocked dbt ephemeral boundary in dbt model chain",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('__dbt_ref("analytics", "stg_orders")',),
        manifest_kind="chain_ephemeral_boundary",
        mock_model_names=("analytics__stg_orders",),
    ),
]

TEST_TARGET_ERROR_TEST_CASES: list[DbtSqlTestTargetErrorTestCase] = [
    DbtSqlTestTargetErrorTestCase(
        description="errors on ambiguous bare dbt expected target",
        manifest_kind="ambiguous",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="ambiguous across packages",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dbt test target has no compiled SQL",
        manifest_kind="missing_compiled_sql",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="has no compiled SQL",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dependency relation cannot be rewritten",
        manifest_kind="unresolved_relation",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="compiled SQL did not contain upstream relation",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dbt and SQLBuild model names overlap",
        manifest_kind="default",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="dbt and SQLBuild models share names: fact_orders",
        project_kind="model_name_collision",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when source dependency relation cannot be rewritten",
        manifest_kind="source_unresolved_relation",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="compiled SQL did not contain upstream relation",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when seed dependency relation cannot be rewritten",
        manifest_kind="seed_unresolved_relation",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="compiled SQL did not contain upstream relation",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when upstream dbt chain model has no compiled SQL",
        manifest_kind="chain_missing_compiled_sql",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="has no compiled SQL",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when upstream dbt chain relation cannot be rewritten",
        manifest_kind="chain_unresolved_relation",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="compiled SQL did not contain upstream relation",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when upstream dbt snapshot is resolved inside a chain",
        manifest_kind="chain_snapshot_boundary",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="snapshot 'snapshot.analytics.stg_orders' cannot be resolved",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when upstream dbt ephemeral model is resolved inside a chain",
        manifest_kind="chain_ephemeral_boundary",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="ephemeral 'model.analytics.stg_orders' cannot be resolved",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dbt source relation clashes with SQLBuild source",
        manifest_kind="source_dependency",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="same relation as SQLBuild source",
        project_kind="source_relation_collision",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dbt seed relation clashes with SQLBuild seed",
        manifest_kind="seed_dependency",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="same relation as SQLBuild seed",
        project_kind="seed_relation_collision",
    ),
    DbtSqlTestTargetErrorTestCase(
        description="errors when dbt seed relation clashes before qualified name is built",
        manifest_kind="seed_dependency",
        expected_model_names=("fact_orders",),
        target_names=("fact_orders",),
        expected_error_fragment="same relation as SQLBuild seed",
        project_kind="seed_relation_collision_unqualified",
    ),
]
FIXTURE_NAME_SUCCESS_TEST_CASES: list[DbtSqlTestFixtureNameTestCase] = [
    DbtSqlTestFixtureNameTestCase(
        description="extends dbt model fixture names",
        fixture_kind="model",
        known_names=set(),
        expected_names={
            "fact_orders",
            "analytics__fact_orders",
            "stg_orders",
            "analytics__stg_orders",
        },
        manifest_kind="default",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="extends ambiguous dbt model fixture names with qualified names only",
        fixture_kind="model",
        known_names=set(),
        expected_names={
            "analytics__fact_orders",
            "finance__fact_orders",
            "stg_orders",
            "analytics__stg_orders",
        },
        manifest_kind="ambiguous",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="extends dbt source fixture names",
        fixture_kind="source",
        known_names=set(),
        expected_names={"raw__orders", "analytics__raw__orders"},
    ),
    DbtSqlTestFixtureNameTestCase(
        description="extends ambiguous dbt source fixture names with qualified names only",
        fixture_kind="source",
        known_names=set(),
        expected_names={"analytics__raw__orders", "finance__raw__orders"},
        manifest_kind="source_ambiguous_fixture",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="extends dbt seed fixture names",
        fixture_kind="seed",
        known_names=set(),
        expected_names={"countries", "analytics__countries"},
        manifest_kind="seed_dependency",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="extends ambiguous dbt seed fixture names with qualified names only",
        fixture_kind="seed",
        known_names=set(),
        expected_names={"analytics__countries", "finance__countries"},
        manifest_kind="seed_ambiguous_fixture",
    ),
]
FIXTURE_NAME_ERROR_TEST_CASES: list[DbtSqlTestFixtureNameTestCase] = [
    DbtSqlTestFixtureNameTestCase(
        description="errors when dbt model fixture name clashes with SQLBuild model",
        fixture_kind="model",
        known_names={"analytics__fact_orders"},
        expected_names=set(),
        expected_error_fragment="conflicts with a SQLBuild model",
        manifest_kind="default",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="errors when dbt source fixture name clashes with SQLBuild source",
        fixture_kind="source",
        known_names={"raw__orders"},
        expected_names=set(),
        expected_error_fragment="conflicts with a SQLBuild source",
    ),
    DbtSqlTestFixtureNameTestCase(
        description="errors when dbt seed fixture name clashes with SQLBuild seed",
        fixture_kind="seed",
        known_names={"countries"},
        expected_names=set(),
        expected_error_fragment="conflicts with a SQLBuild seed",
        manifest_kind="seed_dependency",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_TARGET_TEST_CASES,
    ids=[case.description for case in TEST_TARGET_TEST_CASES],
)
def test_given_dbt_sql_test_target_when_adapting_project_then_adds_compiled_model(
    test_case: DbtSqlTestTargetTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_sql_test_target_success_manifest(
        manifest_kind=test_case.manifest_kind
    )
    project: CompiledProject = build_project_with_expected_sql_test_targets(
        expected_model_names=test_case.expected_model_names,
        sqlbuild_model_names=test_case.sqlbuild_model_names,
        mock_model_names=test_case.mock_model_names,
    )

    target_names: tuple[str, ...] = resolve_dbt_sql_test_target_names(
        project=project,
        manifest=manifest,
        selected_dbt_unique_ids=test_case.selected_dbt_unique_ids,
        select=test_case.select,
    )
    adapted: CompiledProject = adapt_project_for_dbt_sql_tests(
        project=project,
        manifest=manifest,
        target_names=target_names,
    )

    assert target_names == test_case.expected_target_names
    assert tuple(model.name for model in adapted.models) == test_case.adapted_model_names
    raw_payload: object = adapted.sql_tests[0].payload
    assert isinstance(raw_payload, CompiledModelSqlTestPayload)
    payload: CompiledModelSqlTestPayload = raw_payload
    adapted_query_sql: str = payload.model_query_overrides.get(
        adapted.models[0].name, adapted.models[0].query_sql
    )
    for expected_fragment in test_case.expected_query_fragments:
        assert expected_fragment in adapted_query_sql
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in adapted_query_sql


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSqlTestMultipleBoundaryTestCase(
            description="keeps dbt chain boundaries per SQL test",
            expected_test_model_names=(
                ("stg_orders", "fact_orders"),
                ("fact_orders",),
            ),
            expected_query_fragments_by_test=(
                ('fact_orders:__ref("stg_orders")', 'stg_orders:__source("raw__orders")'),
                ('fact_orders:__dbt_ref("analytics", "stg_orders")',),
            ),
            expected_absent_fragments_by_test=(
                ('fact_orders:__dbt_ref("analytics", "stg_orders")',),
                ('fact_orders:__ref("stg_orders")',),
            ),
        )
    ],
    ids=["keeps dbt chain boundaries per SQL test"],
)
def test_given_multiple_dbt_sql_tests_when_adapting_then_keeps_mock_boundaries_per_test(
    test_case: DbtSqlTestMultipleBoundaryTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_sql_test_target_success_manifest(
        manifest_kind="chain_source_dependency"
    )
    project: CompiledProject = build_project_with_multiple_dbt_sql_test_boundaries()

    adapted: CompiledProject = adapt_project_for_dbt_sql_tests(
        project=project,
        manifest=manifest,
        target_names=("fact_orders",),
    )

    sql_test_index: int
    for sql_test_index, sql_test in enumerate(adapted.sql_tests):
        raw_payload: object = sql_test.payload
        assert isinstance(raw_payload, CompiledModelSqlTestPayload)
        payload: CompiledModelSqlTestPayload = raw_payload
        assert payload.expected_model_names == test_case.expected_test_model_names[sql_test_index]
        expected_fragment: str
        for expected_fragment in test_case.expected_query_fragments_by_test[sql_test_index]:
            model_name: str
            fragment: str
            model_name, fragment = expected_fragment.split(":", maxsplit=1)
            assert fragment in payload.model_query_overrides[model_name]
        absent_fragment: str
        for absent_fragment in test_case.expected_absent_fragments_by_test[sql_test_index]:
            model_name, fragment = absent_fragment.split(":", maxsplit=1)
            assert fragment not in payload.model_query_overrides[model_name]


@pytest.mark.parametrize(
    "test_case",
    TEST_TARGET_ERROR_TEST_CASES,
    ids=[case.description for case in TEST_TARGET_ERROR_TEST_CASES],
)
def test_given_invalid_dbt_sql_test_target_when_adapting_project_then_errors(
    test_case: DbtSqlTestTargetErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_sql_test_target_error_manifest(
        manifest_kind=test_case.manifest_kind
    )
    project: CompiledProject = build_dbt_sql_test_target_error_project(
        project_kind=test_case.project_kind
    )

    with pytest.raises(DbtInteropRuntimeError, match=test_case.expected_error_fragment):
        adapt_project_for_dbt_sql_tests(
            project=project,
            manifest=manifest,
            target_names=test_case.target_names,
        )


@pytest.mark.parametrize(
    "test_case",
    FIXTURE_NAME_SUCCESS_TEST_CASES,
    ids=[case.description for case in FIXTURE_NAME_SUCCESS_TEST_CASES],
)
def test_given_dbt_manifest_when_extending_sql_test_fixture_names_then_returns_expected_names(
    test_case: DbtSqlTestFixtureNameTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_sql_test_target_success_manifest(
        manifest_kind=test_case.manifest_kind
    )
    result: set[str] = resolve_dbt_sql_test_fixture_names(
        manifest=manifest,
        fixture_kind=test_case.fixture_kind,
        known_names=test_case.known_names,
    )

    assert result == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    FIXTURE_NAME_ERROR_TEST_CASES,
    ids=[case.description for case in FIXTURE_NAME_ERROR_TEST_CASES],
)
def test_given_dbt_manifest_when_extending_clashing_sql_test_fixture_names_then_errors(
    test_case: DbtSqlTestFixtureNameTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_sql_test_target_success_manifest(
        manifest_kind=test_case.manifest_kind
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_dbt_sql_test_fixture_names(
            manifest=manifest,
            fixture_kind=test_case.fixture_kind,
            known_names=test_case.known_names,
        )
