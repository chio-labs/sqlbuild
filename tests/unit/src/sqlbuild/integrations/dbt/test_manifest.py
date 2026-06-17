from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.integrations.dbt.helpers.manifest import (
    build_dbt_manifest_index,
    resolve_dbt_manifest_model,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtManifestIndexErrorTestCase,
    DbtManifestResolutionErrorTestCase,
    DbtManifestResolutionTestCase,
    DbtManifestSourceIndexTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_manifest_data,
    build_manifest_model_node,
    build_manifest_source_node,
)

MANIFEST_RESOLUTION_TEST_CASES: list[DbtManifestResolutionTestCase] = [
    DbtManifestResolutionTestCase(
        description="resolves unique one arg model",
        manifest_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name='"main"."analytics"."orders"',
                ),
            )
        ),
        package_name=None,
        model_name="orders",
        expected_relation_name='"main"."analytics"."orders"',
    ),
    DbtManifestResolutionTestCase(
        description="resolves package qualified model",
        manifest_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name="analytics.orders",
                ),
                build_manifest_model_node(
                    unique_id="model.stripe.orders",
                    package_name="stripe",
                    name="orders",
                    relation_name="stripe.orders",
                ),
            )
        ),
        package_name="stripe",
        model_name="orders",
        expected_relation_name="stripe.orders",
    ),
    DbtManifestResolutionTestCase(
        description="renders relation from database schema alias",
        manifest_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.stg_orders",
                    package_name="analytics",
                    name="stg_orders",
                    database="warehouse",
                    schema="analytics",
                    alias="orders",
                ),
            )
        ),
        package_name=None,
        model_name="stg_orders",
        expected_relation_name="warehouse.analytics.orders",
    ),
]

MANIFEST_RESOLUTION_ERROR_TEST_CASES: list[DbtManifestResolutionErrorTestCase] = [
    DbtManifestResolutionErrorTestCase(
        description="fails missing one arg model",
        manifest_data=build_manifest_data(nodes=()),
        package_name=None,
        model_name="orders",
        expected_error_fragment="dbt model 'orders' was not found",
    ),
    DbtManifestResolutionErrorTestCase(
        description="fails missing package qualified model",
        manifest_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name="analytics.orders",
                ),
            )
        ),
        package_name="stripe",
        model_name="orders",
        expected_error_fragment="dbt model 'stripe.orders' was not found",
    ),
    DbtManifestResolutionErrorTestCase(
        description="fails ambiguous one arg model",
        manifest_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name="analytics.orders",
                ),
                build_manifest_model_node(
                    unique_id="model.stripe.orders",
                    package_name="stripe",
                    name="orders",
                    relation_name="stripe.orders",
                ),
            )
        ),
        package_name=None,
        model_name="orders",
        expected_error_fragment="dbt model 'orders' is ambiguous across packages",
    ),
]

MANIFEST_SOURCE_INDEX_TEST_CASES: tuple[DbtManifestSourceIndexTestCase, ...] = (
    DbtManifestSourceIndexTestCase(
        description="indexes manifest source nodes by unique id",
        manifest_data=build_manifest_data(
            nodes=(),
            sources=(
                build_manifest_source_node(
                    unique_id="source.analytics.raw.orders",
                    package_name="analytics",
                    source_name="raw",
                    name="orders",
                    relation_name='"warehouse"."raw"."orders"',
                ),
            ),
        ),
        expected_unique_id="source.analytics.raw.orders",
        expected_source_name="raw",
        expected_name="orders",
        expected_relation_name='"warehouse"."raw"."orders"',
    ),
    DbtManifestSourceIndexTestCase(
        description="renders source relation from database schema identifier",
        manifest_data=build_manifest_data(
            nodes=(),
            sources=(
                build_manifest_source_node(
                    unique_id="source.analytics.raw.orders",
                    package_name="analytics",
                    source_name="raw",
                    name="orders",
                    database="warehouse",
                    schema="raw",
                    identifier="orders_table",
                ),
            ),
        ),
        expected_unique_id="source.analytics.raw.orders",
        expected_source_name="raw",
        expected_name="orders",
        expected_relation_name="warehouse.raw.orders_table",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_RESOLUTION_TEST_CASES,
    ids=[case.description for case in MANIFEST_RESOLUTION_TEST_CASES],
)
def test_given_manifest_model_when_resolving_then_returns_expected_relation(
    test_case: DbtManifestResolutionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    model: DbtManifestModel = resolve_dbt_manifest_model(
        manifest=manifest,
        package_name=test_case.package_name,
        name=test_case.model_name,
    )

    assert model.relation_name == test_case.expected_relation_name


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_RESOLUTION_ERROR_TEST_CASES,
    ids=[case.description for case in MANIFEST_RESOLUTION_ERROR_TEST_CASES],
)
def test_given_manifest_lookup_error_when_resolving_then_raises_compile_input_error(
    test_case: DbtManifestResolutionErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_dbt_manifest_model(
            manifest=manifest,
            package_name=test_case.package_name,
            name=test_case.model_name,
        )


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_SOURCE_INDEX_TEST_CASES,
    ids=[case.description for case in MANIFEST_SOURCE_INDEX_TEST_CASES],
)
def test_given_manifest_source_when_indexing_then_source_is_available_by_unique_id(
    test_case: DbtManifestSourceIndexTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    source: DbtManifestSource = manifest.sources_by_unique_id[test_case.expected_unique_id]

    assert source.unique_id == test_case.expected_unique_id
    assert source.source_name == test_case.expected_source_name
    assert source.name == test_case.expected_name
    assert source.relation_name == test_case.expected_relation_name


@pytest.mark.parametrize(
    "test_case",
    [
        DbtManifestIndexErrorTestCase(
            description="fails malformed sources shape",
            manifest_data={"nodes": {}, "sources": []},
            expected_error_fragment="Invalid dbt manifest: sources must be an object",
        )
    ],
    ids=["fails malformed sources shape"],
)
def test_given_manifest_index_error_when_indexing_then_raises_compile_input_error(
    test_case: DbtManifestIndexErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        build_dbt_manifest_index(raw_data=test_case.manifest_data)
