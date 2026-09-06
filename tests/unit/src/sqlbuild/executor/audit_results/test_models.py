"""Tests for deterministic audit result identity."""

import pytest

from sqlbuild.executor.audit_results.models import build_audit_result_id
from tests.unit.src.sqlbuild.executor.audit_results._test_types import (
    AuditResultIdentityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultIdentityTestCase(
            description="same attempt identity",
            run_scope_phase="final",
            first_attempt_key="batch-3:attempt-2",
            second_attempt_key="batch-3:attempt-2",
            expected_equal=True,
            expected_first="46e6126691a2b0cd5524d8c56108f6b6932548d915ea8e61c918020652523552",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_attempt_identity_when_building_result_ids_then_determinism_matches_expectation(
    test_case: AuditResultIdentityTestCase,
) -> None:
    arguments: dict[str, str] = {
        "invocation_id": "invocation-1",
        "run_id": "run-1",
        "binding_key": "orders.not_null",
        "execution_fingerprint": "execution-fingerprint",
        "run_scope_phase": test_case.run_scope_phase,
    }

    first: str = build_audit_result_id(**arguments, attempt_key=test_case.first_attempt_key)
    second: str = build_audit_result_id(**arguments, attempt_key=test_case.second_attempt_key)

    assert (first == second) is test_case.expected_equal
    assert first == test_case.expected_first


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultIdentityTestCase(
            description="different attempt identity",
            run_scope_phase="delta",
            first_attempt_key="batch-1",
            second_attempt_key="batch-2",
            expected_equal=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_different_attempt_identity_when_building_result_ids_then_values_differ(
    test_case: AuditResultIdentityTestCase,
) -> None:
    first: str = build_audit_result_id(
        invocation_id="invocation-1",
        run_id="run-1",
        binding_key="orders.not_null",
        execution_fingerprint="execution-fingerprint",
        run_scope_phase=test_case.run_scope_phase,
        attempt_key=test_case.first_attempt_key,
    )
    second: str = build_audit_result_id(
        invocation_id="invocation-1",
        run_id="run-1",
        binding_key="orders.not_null",
        execution_fingerprint="execution-fingerprint",
        run_scope_phase=test_case.run_scope_phase,
        attempt_key=test_case.second_attempt_key,
    )

    assert (first == second) is test_case.expected_equal
