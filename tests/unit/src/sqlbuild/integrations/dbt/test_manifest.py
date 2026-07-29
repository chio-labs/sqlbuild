from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.integrations.dbt._helpers.manifest.core import (
    build_dbt_manifest_index,
    resolve_dbt_manifest_model,
)
from sqlbuild.integrations.dbt.models import (
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtManifestResolutionTestCase(
            description="resolves one-argument dbt model reference",
            manifest_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.orders",
                        package_name="analytics",
                        name="orders",
                        relation_name="warehouse.analytics.orders",
                    ),
                )
            ),
            package_name=None,
            model_name="orders",
            expected_relation_name="warehouse.analytics.orders",
        ),
        DbtManifestResolutionTestCase(
            description="resolves package-qualified dbt model reference",
            manifest_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.orders",
                        package_name="analytics",
                        name="orders",
                        relation_name="warehouse.analytics.orders",
                    ),
                )
            ),
            package_name="analytics",
            model_name="orders",
            expected_relation_name="warehouse.analytics.orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_model_when_resolving_then_returns_expected_relation(
    test_case: DbtManifestResolutionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    model: DbtManifestModel = resolve_dbt_manifest_model(
        manifest=manifest,
        name=test_case.model_name,
        package_name=test_case.package_name,
    )

    assert model.relation_name == test_case.expected_relation_name


@pytest.mark.parametrize(
    "test_case",
    [
        DbtManifestResolutionErrorTestCase(
            description="rejects unknown model",
            manifest_data=build_manifest_data(nodes=()),
            package_name=None,
            model_name="missing",
            expected_error_fragment="was not found",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_lookup_error_when_resolving_then_raises_compile_input_error(
    test_case: DbtManifestResolutionErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_dbt_manifest_model(
            manifest=manifest,
            name=test_case.model_name,
            package_name=test_case.package_name,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtManifestSourceIndexTestCase(
            description="indexes dbt sources for combined graph and lineage",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        package_name="analytics",
                        source_name="raw",
                        name="orders",
                        relation_name="warehouse.raw.orders",
                    ),
                ),
            ),
            expected_unique_id="source.analytics.raw.orders",
            expected_source_name="raw",
            expected_name="orders",
            expected_relation_name="warehouse.raw.orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_source_when_indexing_then_source_is_available_by_unique_id(
    test_case: DbtManifestSourceIndexTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    source: DbtManifestSource = manifest.sources_by_unique_id[test_case.expected_unique_id]

    assert source.source_name == test_case.expected_source_name
    assert source.name == test_case.expected_name
    assert source.relation_name == test_case.expected_relation_name


@pytest.mark.parametrize(
    "test_case",
    [
        DbtManifestIndexErrorTestCase(
            description="rejects manifest without nodes mapping",
            manifest_data={},
            expected_error_fragment="nodes must be an object",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_index_error_when_indexing_then_raises_compile_input_error(
    test_case: DbtManifestIndexErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        build_dbt_manifest_index(raw_data=test_case.manifest_data)
