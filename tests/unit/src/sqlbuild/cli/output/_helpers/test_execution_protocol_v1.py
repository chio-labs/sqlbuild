"""Execution JSON protocol coverage for microbatch accounting."""

from __future__ import annotations

import pytest

from sqlbuild.cli.output._helpers.execution_protocol_v1 import _format_model_assets
from sqlbuild.executor.run.models import (
    MicrobatchAccountingInterval,
    ModelExecutionResult,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.unit.src.sqlbuild.cli.output._helpers._test_types import (
    MicrobatchExecutionProtocolTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchExecutionProtocolTestCase(
            description="microbatch execution exposes replay accounting",
            expected_run_type="replay_on_change",
            expected_replay_state="complete_with_unknown_fingerprints",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_result_when_formatting_json_then_interval_provenance_is_exposed(
    test_case: MicrobatchExecutionProtocolTestCase,
) -> None:
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="orders",
        status=ExecutionStatus.SUCCESS,
        batch_count=2,
        batch_size="1h",
        microbatch_run_type="replay_on_change",
        microbatch_recovery_batch_count=1,
        microbatch_known_gap_count=1,
        microbatch_unaccounted_interval_count=1,
        microbatch_synthetic_completion_count=1,
        microbatch_unknown_fingerprint_count=1,
        microbatch_contiguous_frontier="2026-01-01T01:00:00",
        microbatch_unaccounted_partition_policy="recover_empty",
        microbatch_replay_requirement_id="requirement-1",
        microbatch_required_model_version_hash="F2",
        microbatch_physical_generation_id="generation-1",
        microbatch_concurrent_enabled=True,
        microbatch_batch_concurrency=2,
        microbatch_global_concurrency=4,
        microbatch_replay_requirement_state="complete_with_unknown_fingerprints",
        microbatch_accounting_intervals=(
            MicrobatchAccountingInterval(
                partition_start="2026-01-01T00:00:00",
                partition_end="2026-01-01T01:00:00",
                accounting_status="synthetic",
                fingerprint_status="unknown",
            ),
        ),
    )

    asset: dict[str, object] = _format_model_assets(results=(result,), plan=None)[0]

    assert asset["microbatch"] == {
        "run_type": test_case.expected_run_type,
        "batch_count": 2,
        "batch_size": "1h",
        "recovery_batch_count": 1,
        "known_gap_count": 1,
        "unaccounted_interval_count": 1,
        "synthetic_completion_count": 1,
        "unknown_fingerprint_count": 1,
        "contiguous_frontier": "2026-01-01T01:00:00",
        "unaccounted_partition_policy": "recover_empty",
        "replay_requirement_id": "requirement-1",
        "required_model_version_hash": "F2",
        "physical_generation_id": "generation-1",
        "concurrent_enabled": True,
        "batch_concurrency": 2,
        "global_concurrency": 4,
        "replay_requirement_state": test_case.expected_replay_state,
        "intervals": [
            {
                "partition_start": "2026-01-01T00:00:00",
                "partition_end": "2026-01-01T01:00:00",
                "accounting_status": "synthetic",
                "fingerprint_status": "unknown",
                "model_version_hash": None,
                "completion_type": None,
                "event_id": None,
            }
        ],
    }
