"""Normalization removes only run-specific noise before engines are compared."""

from __future__ import annotations

import pytest

from scripts.compiler_differential._helpers.comparing.normalize import (
    normalize_artifact_text,
    normalize_stderr,
    strip_manifest_metadata,
    strip_report_fields,
)
from tests.unit.scripts.compiler_differential._helpers.comparing._test_types import (
    NormalizationTestCase,
    PayloadStripTestCase,
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
            description="engine_store_path",
            raw="wrote target/cache/compiler-native-v1/facts",
            expected_text="wrote target/cache/compiler/facts",
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


@pytest.mark.parametrize(
    "test_case",
    [
        PayloadStripTestCase(
            description="compile_report",
            payload={
                "summary": {"models": 2},
                "compile_timings": {"total_ms": 10},
                "compiler_engine": "native",
            },
            expected_payload={"summary": {"models": 2}},
        ),
        PayloadStripTestCase(
            description="non_object_report", payload=[1, 2], expected_payload=[1, 2]
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compile_report_when_stripping_then_only_timings_and_engine_are_removed(
    test_case: PayloadStripTestCase,
) -> None:
    assert strip_report_fields(test_case.payload) == test_case.expected_payload


@pytest.mark.parametrize(
    "test_case",
    [
        PayloadStripTestCase(
            description="manifest_metadata",
            payload={
                "metadata": {
                    "generated_at": "2026-10-06T17:25:10+00:00",
                    "invocation_id": "20261006T172510Z_dee386e8ffa7",
                    "project_name": "orders",
                },
                "nodes": {},
            },
            expected_payload={"metadata": {"project_name": "orders"}, "nodes": {}},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manifest_when_stripping_then_generation_identity_is_removed(
    test_case: PayloadStripTestCase,
) -> None:
    assert strip_manifest_metadata(test_case.payload) == test_case.expected_payload


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
