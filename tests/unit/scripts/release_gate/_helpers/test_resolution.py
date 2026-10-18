import pytest

from scripts.release_gate._helpers.resolution import required_check_passes
from scripts.release_gate.models import CheckRun, CommitStatus
from scripts.release_gate.types import CheckState
from tests.unit.scripts.release_gate._helpers._test_types import RequiredCheckTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        RequiredCheckTestCase(
            description="nothing reported keeps the check expected",
            check_runs=(),
            statuses=(),
            expected_passes=False,
        ),
        RequiredCheckTestCase(
            description="a differently named check run does not count",
            check_runs=(CheckRun(sha="head", name="Suites", conclusion=CheckState.SUCCESS),),
            statuses=(),
            expected_passes=False,
        ),
        RequiredCheckTestCase(
            description="a passing check run alone passes",
            check_runs=(CheckRun(sha="head", name="Verify", conclusion=CheckState.SUCCESS),),
            statuses=(),
            expected_passes=True,
        ),
        RequiredCheckTestCase(
            description="a skipped check run passes",
            check_runs=(CheckRun(sha="head", name="Verify", conclusion=CheckState.SKIPPED),),
            statuses=(),
            expected_passes=True,
        ),
        RequiredCheckTestCase(
            description="a passing commit status alone passes",
            check_runs=(),
            statuses=(CommitStatus(sha="head", context="Verify", state=CheckState.SUCCESS),),
            expected_passes=True,
        ),
        RequiredCheckTestCase(
            description="a later commit status replaces an earlier failure",
            check_runs=(),
            statuses=(
                CommitStatus(sha="head", context="Verify", state=CheckState.FAILURE),
                CommitStatus(sha="head", context="Verify", state=CheckState.SUCCESS),
            ),
            expected_passes=True,
        ),
        RequiredCheckTestCase(
            description="a check run and a commit status sharing the name must both pass",
            check_runs=(CheckRun(sha="head", name="Verify", conclusion=CheckState.SUCCESS),),
            statuses=(CommitStatus(sha="head", context="Verify", state=CheckState.PENDING),),
            expected_passes=False,
        ),
        RequiredCheckTestCase(
            description="a status on an earlier commit does not count",
            check_runs=(),
            statuses=(CommitStatus(sha="earlier", context="Verify", state=CheckState.SUCCESS),),
            expected_passes=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reported_checks_when_resolving_required_check_then_returns_expected(
    test_case: RequiredCheckTestCase,
) -> None:
    passes: bool = required_check_passes(
        name="Verify",
        head_sha="head",
        check_runs=test_case.check_runs,
        statuses=test_case.statuses,
    )

    assert passes is test_case.expected_passes


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
