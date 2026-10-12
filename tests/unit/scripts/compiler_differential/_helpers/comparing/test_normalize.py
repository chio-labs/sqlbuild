"""Normalization removes only run-specific noise from compile outputs."""

from __future__ import annotations

import pytest

from scripts.compiler_differential._helpers.comparing.normalize import (
    normalize_artifact_text,
    normalize_stderr,
)
from tests.unit.scripts.compiler_differential._helpers.comparing._test_types import (
    NormalizationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizationTestCase(
            description="phase_timing",
            raw="Project compile  OK  (0.23s)",
            expected_text="Project compile  OK  (<elapsed>)",
        ),
        NormalizationTestCase(
            description="rules_timing",
            raw="Evaluated rules. (0.02s; built-in 0.00s, custom 12ms)",
            expected_text="Evaluated rules. (<elapsed>; built-in <elapsed>, custom <elapsed>)",
        ),
        NormalizationTestCase(
            description="compiler_store_path",
            raw="wrote target/cache/compiler-native-v1/facts",
            expected_text="wrote target/cache/compiler/facts",
        ),
        NormalizationTestCase(
            description="rules_store_path",
            raw="wrote target/rules-cache-native-v1/bulk",
            expected_text="wrote target/rules-cache/bulk",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stderr_when_normalizing_then_elapsed_times_are_masked(
    test_case: NormalizationTestCase,
) -> None:
    assert normalize_stderr(test_case.raw) == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizationTestCase(
            description="invocation_id",
            raw='"run_id": "20261006T172510Z_dee386e8ffa7"',
            expected_text='"run_id": "<invocation-id>"',
        ),
        NormalizationTestCase(
            description="durations_are_kept_in_artifacts",
            raw="SELECT '5s' AS label",
            expected_text="SELECT '5s' AS label",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_artifact_text_when_normalizing_then_only_run_identity_is_masked(
    test_case: NormalizationTestCase,
) -> None:
    assert normalize_artifact_text(test_case.raw) == test_case.expected_text


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
