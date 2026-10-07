"""Coverage requirements are rejected unless the run captures stages for the seed corpus."""

from __future__ import annotations

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.unit.scripts.compiler_differential.main._test_types import CoverageFlagUsageTestCase

_USAGE_ERROR_EXIT_CODE: int = 2


@pytest.mark.parametrize(
    "test_case",
    [
        CoverageFlagUsageTestCase(
            description="render_coverage_without_captures",
            arguments=("--corpus", "seeds", "--require-render-coverage"),
            expected_message="--require-render-coverage needs --stage-captures and the seeds corpus",
        ),
        CoverageFlagUsageTestCase(
            description="render_coverage_without_seeds",
            arguments=("--corpus", "fixtures", "--stage-captures", "--require-render-coverage"),
            expected_message="--require-render-coverage needs --stage-captures and the seeds corpus",
        ),
        CoverageFlagUsageTestCase(
            description="discovery_coverage_without_captures",
            arguments=("--corpus", "seeds", "--require-discovery-coverage"),
            expected_message=(
                "--require-discovery-coverage needs --stage-captures and the seeds corpus"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_coverage_requirement_without_captured_seeds_when_parsing_then_usage_error(
    test_case: CoverageFlagUsageTestCase, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        _ = run_compiler_differential(list(test_case.arguments))

    assert raised.value.code == _USAGE_ERROR_EXIT_CODE
    assert test_case.expected_message in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
