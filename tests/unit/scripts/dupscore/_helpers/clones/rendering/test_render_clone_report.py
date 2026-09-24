from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.dupscore._helpers.clones.rendering import render_clone_json, render_clone_text
from scripts.dupscore.models import CloneReport
from tests.unit.scripts.dupscore._helpers.clones.rendering._test_types import (
    ForcedMarkerTestCase,
    HiddenCountsTestCase,
)
from tests.unit.scripts.dupscore._helpers.clones.rendering.helpers import (
    member_lines,
    report_with_members,
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


@pytest.mark.parametrize(
    "test_case",
    [
        ForcedMarkerTestCase(
            description="forced members are marked in text and flagged in json",
            forced_flags=(False, True),
            expected_member_lines=(
                "src/sqlbuild/demo/orders.py:1-9 OrdersStore.write_orders (80 tokens)",
                "src/sqlbuild/demo/orders.py:11-19 BaseStore.write_orders (80 tokens) [forced]",
            ),
            expected_json_flags=[False, True],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_forced_members_when_rendering_then_marks_them(
    test_case: ForcedMarkerTestCase,
) -> None:
    report: CloneReport = report_with_members(test_case.forced_flags)

    text: str = render_clone_text(report=report, top=5)
    payload: dict[str, Any] = json.loads(render_clone_json(report=report, top=5))

    assert member_lines(text) == test_case.expected_member_lines
    assert [
        member["forced_override"] for member in payload["clusters"][0]["members"]
    ] == test_case.expected_json_flags
