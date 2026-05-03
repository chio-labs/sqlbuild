"""Unit tests for build progress output helpers."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.shared.helpers.progress import (
    _aggregate_audit_results,
    _AuditDisplayEntry,
    _truncate_name,
)
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    AuditAggregationTestCase,
    TruncateNameTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers.helpers import (
    build_audit_result,
)

TRUNCATE_NAME_TEST_CASES: list[TruncateNameTestCase] = [
    TruncateNameTestCase(
        description="name shorter than width is returned unchanged",
        name="orders",
        width=20,
        expected_result="orders",
    ),
    TruncateNameTestCase(
        description="name exactly at width is returned unchanged",
        name="orders",
        width=6,
        expected_result="orders",
    ),
    TruncateNameTestCase(
        description="name longer than width is truncated with ellipsis",
        name="very_long_model_name_that_exceeds_limit",
        width=20,
        expected_result="very_long_model_n...",
    ),
    TruncateNameTestCase(
        description="name one char over width truncates correctly",
        name="abcdefgh",
        width=7,
        expected_result="abcd...",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TRUNCATE_NAME_TEST_CASES,
    ids=[case.description for case in TRUNCATE_NAME_TEST_CASES],
)
def test_given_name_and_width_when_truncating_then_returns_expected_result(
    test_case: TruncateNameTestCase,
) -> None:
    result: str = _truncate_name(test_case.name, test_case.width)

    assert result == test_case.expected_result


AUDIT_AGGREGATION_TEST_CASES: list[AuditAggregationTestCase] = [
    AuditAggregationTestCase(
        description="final-only audits produce one entry per audit with audit label",
        audit_results=(
            build_audit_result(name="not_null", outcome=AuditOutcome.PASS, column_name="id"),
            build_audit_result(name="unique", outcome=AuditOutcome.PASS, column_name="id"),
        ),
        expected_entry_count=2,
        expected_labels=("audit", "audit"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(1, 1),
        expected_batch_passes=(1, 1),
    ),
    AuditAggregationTestCase(
        description="delta_and_final audits produce separate delta and final entries",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(1, 1),
        expected_batch_passes=(1, 1),
    ),
    AuditAggregationTestCase(
        description="multiple delta batches aggregate into one entry with batch count",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(3, 1),
        expected_batch_passes=(3, 1),
    ),
    AuditAggregationTestCase(
        description="worst outcome across batches is reported when one batch fails",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.ERROR,
                column_name="id",
                row_count=5,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.ERROR, AuditOutcome.PASS),
        expected_batch_totals=(3, 1),
        expected_batch_passes=(2, 1),
    ),
    AuditAggregationTestCase(
        description="warn is worst outcome when no errors present",
        audit_results=(
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.PASS,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.WARN,
                row_count=2,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.PASS,
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.WARN, AuditOutcome.PASS),
        expected_batch_totals=(2, 1),
        expected_batch_passes=(1, 1),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    AUDIT_AGGREGATION_TEST_CASES,
    ids=[case.description for case in AUDIT_AGGREGATION_TEST_CASES],
)
def test_given_audit_results_when_aggregating_then_produces_expected_entries(
    test_case: AuditAggregationTestCase,
) -> None:
    entries: list[_AuditDisplayEntry] = _aggregate_audit_results(test_case.audit_results)

    assert len(entries) == test_case.expected_entry_count

    idx: int
    for idx in range(test_case.expected_entry_count):
        assert entries[idx].label == test_case.expected_labels[idx], (
            f"entry {idx}: expected label {test_case.expected_labels[idx]!r}, "
            f"got {entries[idx].label!r}"
        )
        assert entries[idx].outcome == test_case.expected_outcomes[idx], (
            f"entry {idx}: expected outcome {test_case.expected_outcomes[idx]!r}, "
            f"got {entries[idx].outcome!r}"
        )
        assert entries[idx].batch_total == test_case.expected_batch_totals[idx], (
            f"entry {idx}: expected batch_total {test_case.expected_batch_totals[idx]}, "
            f"got {entries[idx].batch_total}"
        )
        assert entries[idx].batch_pass == test_case.expected_batch_passes[idx], (
            f"entry {idx}: expected batch_pass {test_case.expected_batch_passes[idx]}, "
            f"got {entries[idx].batch_pass}"
        )
