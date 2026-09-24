from __future__ import annotations

import json

import pytest

from scripts.dupscore._helpers.clones.rendering import render_clone_json, render_clone_text
from scripts.dupscore.models import CloneReport
from tests.unit.scripts.dupscore._helpers.clones.rendering._test_types import (
    HiddenCountsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HiddenCountsTestCase(
            description="summary reports allowlisted pairs and contract-exempt members",
            allowlisted_pairs=2,
            contract_exempt_members=5,
            expected_summary_fragment=(
                "2 allowlisted pairs hidden; 5 contract-exempt members hidden"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hidden_counts_when_rendering_then_text_and_json_report_them(
    test_case: HiddenCountsTestCase,
) -> None:
    report: CloneReport = CloneReport(
        since=None,
        unit_counts={"python": 3},
        allowlisted_pairs=test_case.allowlisted_pairs,
        contract_exempt_members=test_case.contract_exempt_members,
        clusters=(),
    )

    text: str = render_clone_text(report=report, top=5)
    payload: dict[str, object] = json.loads(render_clone_json(report=report, top=5))

    assert test_case.expected_summary_fragment in text.splitlines()[0]
    assert payload["allowlisted_pairs"] == test_case.allowlisted_pairs
    assert payload["contract_exempt_members"] == test_case.contract_exempt_members
