"""reuse_from proof reuse for final model audits."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run._helpers.reuse.audit import reused_final_audit_results_by_binding_key
from sqlbuild.executor.run._helpers.reuse.fingerprint_metadata import (
    model_fingerprint_metadata_with_audit_gate,
)
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    ReusedFinalAuditResultsTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import (
    build_fingerprint_audit_plan_entry_with_options,
    build_fingerprint_audit_result,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReusedFinalAuditResultsTestCase(
            description="audit reading only its target lineage reuses origin proof",
            reads_outside_target_lineage=False,
            expected_reused=True,
        ),
        ReusedFinalAuditResultsTestCase(
            description="audit reading resources outside its target lineage always re-runs",
            reads_outside_target_lineage=True,
            expected_reused=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_origin_proof_when_reusing_final_audits_then_only_lineage_audits_reuse(
    test_case: ReusedFinalAuditResultsTestCase,
) -> None:
    audit: AuditPlanEntry = replace(
        build_fingerprint_audit_plan_entry_with_options(),
        reads_outside_target_lineage=test_case.reads_outside_target_lineage,
    )
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(build_fingerprint_audit_result(outcome="pass"),),
        run_id="origin_run",
    )

    reused: dict[str, AuditExecutionResult] = reused_final_audit_results_by_binding_key(
        metadata_json=metadata_json, model_audits=(audit,)
    )

    assert bool(reused) is test_case.expected_reused


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
