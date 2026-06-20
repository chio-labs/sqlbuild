from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.sql_test_targets import (
    adapt_project_for_dbt_sql_tests,
    resolve_dbt_sql_test_target_names,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtSqlTestFixtureNameTestCase,
    DbtSqlTestTargetErrorTestCase,
    DbtSqlTestTargetTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_dbt_sql_test_target_error_manifest,
    build_dbt_sql_test_target_error_project,
    build_dbt_sql_test_target_success_manifest,
    build_project_with_expected_sql_test_targets,
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
            'from __dbt_ref("analytics", "stg_orders")',
            "where amount_cents > 0",
        ),
        expected_absent_fragments=("{{ ref('stg_orders') }}",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts qualified dbt expected target",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("analytics.fact_orders",),
        expected_target_names=("analytics__fact_orders",),
        expected_model_names=("analytics__fact_orders",),
        expected_query_fragments=('__dbt_ref("analytics", "stg_orders")',),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from unquoted relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("analytics", "stg_orders")',),
        manifest_kind="unquoted",
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from three-part relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("analytics", "stg_orders")',),
        manifest_kind="three_part",
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from aliased relation",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('from __dbt_ref("analytics", "stg_orders")',),
        manifest_kind="alias",
    ),
    DbtSqlTestTargetTestCase(
        description="does not target dbt model when SQLBuild model owns name",
        selected_dbt_unique_ids=("model.analytics.fact_orders",),
        select=("fact_orders",),
        expected_target_names=(),
        expected_model_names=("fact_orders",),
        expected_query_fragments=("select 1",),
        sqlbuild_model_names=("fact_orders",),
    ),
    DbtSqlTestTargetTestCase(
        description="adapts selected dbt model from selected test node shape",
        selected_dbt_unique_ids=("test.analytics.not_null_fact_orders_order_id",),
        select=("fact_orders",),
        expected_target_names=("fact_orders",),
        expected_model_names=("fact_orders",),
        expected_query_fragments=('__dbt_ref("analytics", "stg_orders")',),
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
    assert tuple(model.name for model in adapted.models) == test_case.expected_model_names
    adapted_query_sql: str = adapted.models[0].query_sql
    for expected_fragment in test_case.expected_query_fragments:
        assert expected_fragment in adapted_query_sql
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in adapted_query_sql


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
