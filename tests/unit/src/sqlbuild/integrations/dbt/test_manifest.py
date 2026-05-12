from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.integrations.dbt.helpers.manifest import (
    build_dbt_manifest_index,
    resolve_dbt_manifest_model,
)
from sqlbuild.integrations.dbt.models import DbtManifestIndex, DbtManifestModel
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtManifestResolutionErrorTestCase,
    DbtManifestResolutionTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_manifest_data,
    build_manifest_model_node,
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
