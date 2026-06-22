from __future__ import annotations

from pathlib import Path

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
    DbtSeedContentIdentityTestCase,
    DbtSeedIdentityTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_manifest_data,
    build_manifest_model_node,
    build_manifest_seed_node,
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


SEED_IDENTITY_TEST_CASES: list[DbtSeedIdentityTestCase] = [
    DbtSeedIdentityTestCase(
        description="same checksum and config produces the same identity",
        checksum="abc123",
        config_overrides=None,
        other_checksum="abc123",
        other_config_overrides=None,
        expected_same_identity=True,
    ),
    DbtSeedIdentityTestCase(
        description="changed file checksum produces a different identity",
        checksum="abc123",
        config_overrides=None,
        other_checksum="def456",
        other_config_overrides=None,
        expected_same_identity=False,
    ),
    DbtSeedIdentityTestCase(
        description="config-only column_types change produces a different identity",
        checksum="abc123",
        config_overrides=None,
        other_checksum="abc123",
        other_config_overrides={"column_types": {"amount": "bigint"}},
        expected_same_identity=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SEED_IDENTITY_TEST_CASES,
    ids=[case.description for case in SEED_IDENTITY_TEST_CASES],
)
def test_given_seed_nodes_when_indexing_then_identity_hash_reflects_content_and_config(
    test_case: DbtSeedIdentityTestCase,
) -> None:
    index: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_seed_node(
                    unique_id="seed.analytics.left",
                    name="left",
                    checksum=test_case.checksum,
                    config_overrides=test_case.config_overrides,
                ),
                build_manifest_seed_node(
                    unique_id="seed.analytics.right",
                    name="right",
                    checksum=test_case.other_checksum,
                    config_overrides=test_case.other_config_overrides,
                ),
            )
        )
    )

    left_identity: str | None = index.seeds_by_unique_id["seed.analytics.left"].identity_hash
    right_identity: str | None = index.seeds_by_unique_id["seed.analytics.right"].identity_hash

    assert left_identity is not None
    assert right_identity is not None
    assert (left_identity == right_identity) is test_case.expected_same_identity


SEED_CONTENT_IDENTITY_TEST_CASES: list[DbtSeedContentIdentityTestCase] = [
    DbtSeedContentIdentityTestCase(
        description="same content (same stale checksum) keeps identity stable",
        left_content="id,name\n1,a\n2,b\n",
        right_content="id,name\n1,a\n2,b\n",
        expected_same_identity=True,
        expected_warning=False,
    ),
    DbtSeedContentIdentityTestCase(
        description="changed content with an unchanged checksum still changes identity",
        left_content="id,name\n1,a\n2,b\n",
        right_content="id,name\n1,a\n2,c\n",
        expected_same_identity=False,
        expected_warning=False,
    ),
    DbtSeedContentIdentityTestCase(
        description="newline-only differences are normalized and do not change identity",
        left_content="id,name\n1,a\n2,b\n",
        right_content="id,name\r\n1,a\r\n2,b",
        expected_same_identity=True,
        expected_warning=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SEED_CONTENT_IDENTITY_TEST_CASES,
    ids=[case.description for case in SEED_CONTENT_IDENTITY_TEST_CASES],
)
def test_given_seed_files_when_indexing_then_independent_content_hash_detects_changes(
    test_case: DbtSeedContentIdentityTestCase,
    tmp_path: Path,
) -> None:
    left_dir: Path = tmp_path / "left"
    right_dir: Path = tmp_path / "right"
    (left_dir / "seeds").mkdir(parents=True)
    (right_dir / "seeds").mkdir(parents=True)
    (left_dir / "seeds" / "s.csv").write_text(test_case.left_content, encoding="utf-8")
    (right_dir / "seeds" / "s.csv").write_text(test_case.right_content, encoding="utf-8")

    index: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_seed_node(
                    unique_id="seed.analytics.left",
                    name="left",
                    checksum="stale",
                    root_path=str(left_dir),
                    original_file_path="seeds/s.csv",
                ),
                build_manifest_seed_node(
                    unique_id="seed.analytics.right",
                    name="right",
                    checksum="stale",
                    root_path=str(right_dir),
                    original_file_path="seeds/s.csv",
                ),
            )
        )
    )

    left_identity: str | None = index.seeds_by_unique_id["seed.analytics.left"].identity_hash
    right_identity: str | None = index.seeds_by_unique_id["seed.analytics.right"].identity_hash

    assert left_identity is not None
    assert right_identity is not None
    assert (left_identity == right_identity) is test_case.expected_same_identity
    assert bool(index.seed_identity_warnings) is test_case.expected_warning


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedContentIdentityTestCase(
            description="missing seed file falls back to checksum and warns",
            left_content="",
            right_content="",
            expected_same_identity=True,
            expected_warning=True,
        )
    ],
    ids=["missing seed file falls back to checksum and warns"],
)
def test_given_unreadable_seed_file_when_indexing_then_falls_back_with_warning(
    test_case: DbtSeedContentIdentityTestCase,
    tmp_path: Path,
) -> None:
    index: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_seed_node(
                    unique_id="seed.analytics.missing",
                    name="missing",
                    checksum="abc123",
                    root_path=str(tmp_path),
                    original_file_path="seeds/does_not_exist.csv",
                ),
            )
        )
    )

    seed_identity: str | None = index.seeds_by_unique_id["seed.analytics.missing"].identity_hash

    assert seed_identity is not None
    assert bool(index.seed_identity_warnings) is test_case.expected_warning
