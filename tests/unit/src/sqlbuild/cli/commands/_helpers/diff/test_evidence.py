"""Tests for bounded diff example evidence."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.diff.evidence import (
    display_example_value,
    render_example_pair,
)
from sqlbuild.cli.commands.models import DiffExampleRenderOptions, RenderedDiffExampleValue
from tests.unit.src.sqlbuild.cli.commands._helpers.diff._test_types import (
    RenderDiffEvidenceTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderDiffEvidenceTestCase(
            description="late text difference keeps nearby context",
            left_value=("a" * 200) + "left-tail",
            right_value=("a" * 200) + "right-tail",
            options=DiffExampleRenderOptions(max_value_length=30),
            expected_left_fragment="left-tail",
            expected_right_fragment="right-tail",
            expected_first_difference=200,
            expected_truncated=True,
            expected_suppressed=False,
        ),
        RenderDiffEvidenceTestCase(
            description="suppression retains lengths without values",
            left_value="left-private-value",
            right_value="right-private-value",
            options=DiffExampleRenderOptions(max_value_length=30, suppress_values=True),
            expected_left_fragment="18 chars",
            expected_right_fragment="19 chars",
            expected_first_difference=0,
            expected_truncated=False,
            expected_suppressed=True,
        ),
        RenderDiffEvidenceTestCase(
            description="explicit unlimited rendering preserves complete values",
            left_value=("a" * 200) + "left-tail",
            right_value=("a" * 200) + "right-tail",
            options=DiffExampleRenderOptions(max_value_length=None),
            expected_left_fragment=("a" * 200) + "left-tail",
            expected_right_fragment=("a" * 200) + "right-tail",
            expected_first_difference=200,
            expected_truncated=False,
            expected_suppressed=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unequal_values_when_rendering_evidence_then_bounds_are_explicit(
    test_case: RenderDiffEvidenceTestCase,
) -> None:
    left: RenderedDiffExampleValue
    right: RenderedDiffExampleValue
    left, right = render_example_pair(
        left_value=test_case.left_value,
        right_value=test_case.right_value,
        options=test_case.options,
    )

    assert test_case.expected_left_fragment in display_example_value(left)
    assert test_case.expected_right_fragment in display_example_value(right)
    assert left.first_difference == test_case.expected_first_difference
    assert right.first_difference == test_case.expected_first_difference
    assert left.truncated is test_case.expected_truncated
    assert right.truncated is test_case.expected_truncated
    assert left.suppressed is test_case.expected_suppressed
    assert right.suppressed is test_case.expected_suppressed
