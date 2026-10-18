"""Model how a ruleset resolves one required check name on a pull request head."""

from __future__ import annotations

from scripts.release_gate.constants import PASSING_STATES
from scripts.release_gate.models import CheckRun, CommitStatus
from scripts.release_gate.types import CheckState


def required_check_passes(
    *,
    name: str,
    head_sha: str,
    check_runs: tuple[CheckRun, ...],
    statuses: tuple[CommitStatus, ...],
) -> bool:
    """Return whether the required check `name` lets the pull request at `head_sha` merge."""
    reported: list[CheckState] = [
        run.conclusion for run in check_runs if run.sha == head_sha and run.name == name
    ]
    reported.extend(
        [status.state for status in statuses if status.sha == head_sha and status.context == name][
            -1:
        ]
    )
    return bool(reported) and all(state in PASSING_STATES for state in reported)
