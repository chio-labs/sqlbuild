"""Tests for active virtual microbatch replay retention roots."""

from __future__ import annotations

import pytest

from sqlbuild.virtual.state._helpers.state_lifecycle.microbatch_replay_retention import (
    active_microbatch_replay_roots,
)
from sqlbuild.virtual.state.models import MicrobatchReplayRoot
from tests.unit.src.sqlbuild.virtual.state._helpers._test_types import (
    MicrobatchReplayRetentionTestCase,
)
from tests.unit.src.sqlbuild.virtual.state._helpers.helpers import (
    virtual_replay_completion_for_test,
    virtual_replay_requirement_for_test,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchReplayRetentionTestCase(
            description="partial latest replay protects its physical version",
            events=(
                virtual_replay_requirement_for_test(
                    version_hash="F2", event_id="requirement-F2", created_second=0
                ),
                virtual_replay_completion_for_test(
                    version_hash="F2",
                    event_id="completion-F2-1",
                    requirement_id="requirement-F2",
                    start="0",
                    end="1",
                    created_second=1,
                ),
            ),
            expected_roots=(
                MicrobatchReplayRoot(
                    model_name="orders",
                    version_hash="F2",
                    previous_version_hash="previous",
                ),
            ),
        ),
        MicrobatchReplayRetentionTestCase(
            description="verified latest replay releases its physical version",
            events=(
                virtual_replay_requirement_for_test(
                    version_hash="F2", event_id="requirement-F2", created_second=0
                ),
                virtual_replay_completion_for_test(
                    version_hash="F2",
                    event_id="completion-F2",
                    requirement_id="requirement-F2",
                    start="0",
                    end="2",
                    created_second=1,
                ),
            ),
            expected_roots=(),
        ),
        MicrobatchReplayRetentionTestCase(
            description="new complete requirement supersedes incomplete old version",
            events=(
                virtual_replay_requirement_for_test(
                    version_hash="F2", event_id="requirement-F2", created_second=0
                ),
                virtual_replay_requirement_for_test(
                    version_hash="F3", event_id="requirement-F3", created_second=1
                ),
                virtual_replay_completion_for_test(
                    version_hash="F3",
                    event_id="completion-F3",
                    requirement_id="requirement-F3",
                    start="0",
                    end="2",
                    created_second=2,
                ),
            ),
            expected_roots=(),
        ),
        MicrobatchReplayRetentionTestCase(
            description="new all-failed requirement supersedes incomplete old version",
            events=(
                virtual_replay_requirement_for_test(
                    version_hash="F2", event_id="requirement-F2", created_second=0
                ),
                virtual_replay_requirement_for_test(
                    version_hash="F3", event_id="requirement-F3", created_second=1
                ),
            ),
            expected_roots=(
                MicrobatchReplayRoot(
                    model_name="orders",
                    version_hash="F3",
                    previous_version_hash="previous",
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_replay_history_when_projecting_retention_then_only_active_versions_are_roots(
    test_case: MicrobatchReplayRetentionTestCase,
) -> None:
    roots: tuple[MicrobatchReplayRoot, ...] = active_microbatch_replay_roots(
        events=test_case.events
    )

    assert roots == test_case.expected_roots


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
