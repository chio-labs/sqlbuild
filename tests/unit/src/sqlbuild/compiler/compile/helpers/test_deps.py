from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.helpers.deps import (
    audit_scope_deps,
    model_build_deps,
    sql_test_scope_deps,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompileSqlReference
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.shared.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    AuditScopeDepsTestCase,
    ModelBuildDepsTestCase,
    SqlTestScopeDepsTestCase,
)

MODEL_BUILD_DEPS_TEST_CASES: list[ModelBuildDepsTestCase] = [
    ModelBuildDepsTestCase(
        description="maps model source and dbt references to typed build deps",
        references=(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.DBT_REF, ref_name="dbt_customers"),
        ),
        expected_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="stg_orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.DBT_REF, name="dbt_customers"),
        ),
    ),
    ModelBuildDepsTestCase(
        description="dedupes repeated model deps while preserving first seen order",
        references=(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
        ),
        expected_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="stg_orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders"),
        ),
    ),
    ModelBuildDepsTestCase(
        description="seed reference produces a SEED typed dep key",
        references=(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.SEED, ref_name="waffle_types"),
        ),
        expected_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="stg_orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.SEED, name="waffle_types"),
        ),
    ),
]

AUDIT_SCOPE_DEPS_TEST_CASES: list[AuditScopeDepsTestCase] = [
    AuditScopeDepsTestCase(
        description="combines audit references with attached model target",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),),
        attached_target_kind="model",
        attached_target_name="orders",
        expected_scope_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        ),
    ),
    AuditScopeDepsTestCase(
        description="dedupes attached source target already present in refs",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),),
        attached_target_kind="source",
        attached_target_name="raw_orders",
        expected_scope_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders"),
        ),
    ),
]

SQL_TEST_SCOPE_DEPS_TEST_CASES: list[SqlTestScopeDepsTestCase] = [
    SqlTestScopeDepsTestCase(
        description="uses expected models as sql test scope deps",
        expected_model_names=("orders", "daily_revenue"),
        expected_scope_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="daily_revenue"),
        ),
    ),
    SqlTestScopeDepsTestCase(
        description="dedupes repeated expected model names",
        expected_model_names=("orders", "orders"),
        expected_scope_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MODEL_BUILD_DEPS_TEST_CASES,
    ids=[case.description for case in MODEL_BUILD_DEPS_TEST_CASES],
)
def test_given_sql_references_when_deriving_model_build_deps_then_returns_typed_object_keys(
    test_case: ModelBuildDepsTestCase,
) -> None:
    deps: tuple[CompiledObjectKey, ...] = model_build_deps(
        references=test_case.references, seed_names=test_case.seed_names
    )

    assert deps == test_case.expected_deps


@pytest.mark.parametrize(
    "test_case",
    AUDIT_SCOPE_DEPS_TEST_CASES,
    ids=[case.description for case in AUDIT_SCOPE_DEPS_TEST_CASES],
)
def test_given_audit_refs_and_target_when_deriving_scope_deps_then_returns_scope_keys(
    test_case: AuditScopeDepsTestCase,
) -> None:
    deps: tuple[CompiledObjectKey, ...] = audit_scope_deps(
        references=test_case.references,
        attached_target_kind=test_case.attached_target_kind,
        attached_target_name=test_case.attached_target_name,
    )

    assert deps == test_case.expected_scope_deps


@pytest.mark.parametrize(
    "test_case",
    SQL_TEST_SCOPE_DEPS_TEST_CASES,
    ids=[case.description for case in SQL_TEST_SCOPE_DEPS_TEST_CASES],
)
def test_given_expected_models_when_deriving_sql_test_scope_deps_then_returns_model_keys(
    test_case: SqlTestScopeDepsTestCase,
) -> None:
    deps: tuple[CompiledObjectKey, ...] = sql_test_scope_deps(
        expected_model_names=test_case.expected_model_names
    )

    assert deps == test_case.expected_scope_deps
