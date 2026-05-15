"""Tests for audit severity resolution, run scope resolution, and attached audit ref validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.attachment import (
    resolve_audit_run_scope,
    resolve_audit_severity,
    validate_audit_references,
    validate_model_attached_audit_references,
)
from sqlbuild.compiler.compile.models.core import CompileSqlReference
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind
from sqlbuild.compiler.discovery.models import DiscoveredAuditFile
from sqlbuild.shared.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    ResolveAuditRunScopeErrorTestCase,
    ResolveAuditRunScopeTestCase,
    ResolveAuditSeverityTestCase,
    ValidateAuditRefsErrorTestCase,
    ValidateModelAttachedAuditRefsTestCase,
)

SEVERITY_VALID_TEST_CASES: list[ResolveAuditSeverityTestCase] = [
    ResolveAuditSeverityTestCase(
        description="instance severity wins over project default",
        instance_severity="error",
        default_severity="warn",
        expected_severity="error",
    ),
    ResolveAuditSeverityTestCase(
        description="project default used when instance is None",
        instance_severity=None,
        default_severity="warn",
        expected_severity="warn",
    ),
    ResolveAuditSeverityTestCase(
        description="falls back to error when instance and project default are None",
        instance_severity=None,
        default_severity=None,
        expected_severity="error",
    ),
    ResolveAuditSeverityTestCase(
        description="instance warn is valid",
        instance_severity="warn",
        default_severity=None,
        expected_severity="warn",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SEVERITY_VALID_TEST_CASES,
    ids=[case.description for case in SEVERITY_VALID_TEST_CASES],
)
def test_given_valid_severity_inputs_when_resolving_then_returns_expected(
    test_case: ResolveAuditSeverityTestCase,
) -> None:
    result: str = resolve_audit_severity(
        instance_severity=test_case.instance_severity,
        default_severity=test_case.default_severity,
        audit_label="test audit",
    )

    assert result == test_case.expected_severity


SEVERITY_ERROR_TEST_CASES: list[ResolveAuditSeverityTestCase] = [
    ResolveAuditSeverityTestCase(
        description="unknown instance severity raises compile error",
        instance_severity="critical",
        default_severity=None,
        expected_error_fragment="unknown severity",
    ),
    ResolveAuditSeverityTestCase(
        description="unknown default severity raises compile error",
        instance_severity=None,
        default_severity="critical",
        expected_error_fragment="unknown value",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SEVERITY_ERROR_TEST_CASES,
    ids=[case.description for case in SEVERITY_ERROR_TEST_CASES],
)
def test_given_invalid_severity_inputs_when_resolving_then_raises(
    test_case: ResolveAuditSeverityTestCase,
) -> None:
    assert test_case.expected_error_fragment is not None

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_audit_severity(
            instance_severity=test_case.instance_severity,
            default_severity=test_case.default_severity,
            audit_label="test audit",
        )


RUN_SCOPE_VALID_TEST_CASES: list[ResolveAuditRunScopeTestCase] = [
    ResolveAuditRunScopeTestCase(
        description="instance run_scope wins over project default",
        instance_run_scope="delta_and_final",
        default_run_scope="final",
        expected_run_scope="delta_and_final",
    ),
    ResolveAuditRunScopeTestCase(
        description="project default used when instance is None",
        instance_run_scope=None,
        default_run_scope="delta_and_final",
        expected_run_scope="delta_and_final",
    ),
    ResolveAuditRunScopeTestCase(
        description="falls back to delta_and_final when both are None",
        instance_run_scope=None,
        default_run_scope=None,
        expected_run_scope=AuditRunScope.DELTA_AND_FINAL,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RUN_SCOPE_VALID_TEST_CASES,
    ids=[case.description for case in RUN_SCOPE_VALID_TEST_CASES],
)
def test_given_valid_run_scope_inputs_when_resolving_then_returns_expected(
    test_case: ResolveAuditRunScopeTestCase,
) -> None:
    result: str = resolve_audit_run_scope(
        instance_run_scope=test_case.instance_run_scope,
        default_run_scope=test_case.default_run_scope,
    )

    assert result == test_case.expected_run_scope


RUN_SCOPE_ERROR_TEST_CASES: list[ResolveAuditRunScopeErrorTestCase] = [
    ResolveAuditRunScopeErrorTestCase(
        description="unknown instance run_scope raises compile error",
        instance_run_scope="delta_only",
        default_run_scope=None,
        expected_error_fragment="unknown audit run_scope",
    ),
    ResolveAuditRunScopeErrorTestCase(
        description="unknown default run_scope raises compile error",
        instance_run_scope=None,
        default_run_scope="delta_only",
        expected_error_fragment="unknown value",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RUN_SCOPE_ERROR_TEST_CASES,
    ids=[case.description for case in RUN_SCOPE_ERROR_TEST_CASES],
)
def test_given_invalid_run_scope_inputs_when_resolving_then_raises(
    test_case: ResolveAuditRunScopeErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        resolve_audit_run_scope(
            instance_run_scope=test_case.instance_run_scope,
            default_run_scope=test_case.default_run_scope,
        )


ATTACHED_REFS_VALID_TEST_CASES: list[ValidateModelAttachedAuditRefsTestCase] = [
    ValidateModelAttachedAuditRefsTestCase(
        description="model-attached audit referencing attached model passes",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),),
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
    ),
    ValidateModelAttachedAuditRefsTestCase(
        description="source-attached audit skips model ref check",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),),
        attached_target_kind=AttachedAuditTargetKind.SOURCE,
        attached_target_name="raw_orders",
    ),
    ValidateModelAttachedAuditRefsTestCase(
        description="model-attached audit with multiple refs including attached model passes",
        references=(
            CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
            CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_data"),
        ),
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ATTACHED_REFS_VALID_TEST_CASES,
    ids=[case.description for case in ATTACHED_REFS_VALID_TEST_CASES],
)
def test_given_valid_attached_audit_refs_when_validating_then_passes(
    test_case: ValidateModelAttachedAuditRefsTestCase,
) -> None:
    validate_model_attached_audit_references(
        references=test_case.references,
        attached_target_kind=test_case.attached_target_kind,
        attached_target_name=test_case.attached_target_name,
        audit_label="test audit",
    )

    assert test_case.expected_valid


ATTACHED_REFS_ERROR_TEST_CASES: list[ValidateModelAttachedAuditRefsTestCase] = [
    ValidateModelAttachedAuditRefsTestCase(
        description="model-attached audit without ref to attached model raises",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),),
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
        expected_valid=False,
        expected_error_fragment="must reference the attached model",
    ),
    ValidateModelAttachedAuditRefsTestCase(
        description="model-attached audit referencing wrong model raises",
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="customers"),),
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
        expected_valid=False,
        expected_error_fragment="must reference the attached model",
    ),
    ValidateModelAttachedAuditRefsTestCase(
        description="model-attached audit with no refs at all raises",
        references=(),
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
        expected_valid=False,
        expected_error_fragment="must reference the attached model",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ATTACHED_REFS_ERROR_TEST_CASES,
    ids=[case.description for case in ATTACHED_REFS_ERROR_TEST_CASES],
)
def test_given_invalid_attached_audit_refs_when_validating_then_raises(
    test_case: ValidateModelAttachedAuditRefsTestCase,
) -> None:
    assert test_case.expected_error_fragment is not None

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        validate_model_attached_audit_references(
            references=test_case.references,
            attached_target_kind=test_case.attached_target_kind,
            attached_target_name=test_case.attached_target_name,
            audit_label="test audit",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ValidateAuditRefsErrorTestCase(
            description="dbt ref in audit raises compile error",
            references=(CompileSqlReference(ref_kind=SqlReferenceKind.DBT_REF, ref_name="orders"),),
            expected_error_fragment="audit dbt model checks belong in dbt",
        ),
    ],
    ids=["dbt ref in audit raises compile error"],
)
def test_given_invalid_audit_refs_when_validating_then_raises(
    test_case: ValidateAuditRefsErrorTestCase,
) -> None:
    audit_file: DiscoveredAuditFile = DiscoveredAuditFile(
        file_path=Path("audits/dbt_model_check.sql"),
        relative_path=Path("audits/dbt_model_check.sql"),
        contents="",
        blocks=(),
    )

    with pytest.raises(
        CompileInputError,
        match=test_case.expected_error_fragment,
    ):
        validate_audit_references(
            references=test_case.references,
            audit_file=audit_file,
            known_model_names=set(),
            known_seed_names=set(),
            known_source_names=set(),
        )
