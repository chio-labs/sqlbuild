from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.lineage.execution import _requires_compiled_graph
from sqlbuild.cli.commands.models import LineageCommandRequest
from tests.unit.src.sqlbuild.cli.commands._helpers.lineage._test_types import (
    LineageCompiledGraphRequirementTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        LineageCompiledGraphRequirementTestCase(
            description="relation target uses structural lineage",
            target="fact_orders",
            select=(),
            include_uses=False,
            expected_compiled_graph_required=False,
        ),
        LineageCompiledGraphRequirementTestCase(
            description="selector uses structural lineage",
            target=None,
            select=("fact_orders+",),
            include_uses=False,
            expected_compiled_graph_required=False,
        ),
        LineageCompiledGraphRequirementTestCase(
            description="column target retains column analysis",
            target="fact_orders.order_id",
            select=(),
            include_uses=False,
            expected_compiled_graph_required=True,
        ),
        LineageCompiledGraphRequirementTestCase(
            description="semantic uses retain the compiled graph",
            target="fact_orders",
            select=(),
            include_uses=True,
            expected_compiled_graph_required=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_lineage_request_when_checking_analysis_requirement_then_matches_target_granularity(
    test_case: LineageCompiledGraphRequirementTestCase,
) -> None:
    request: LineageCommandRequest = LineageCommandRequest(
        project_dir=None,
        target=test_case.target,
        select=test_case.select,
        include_uses=test_case.include_uses,
    )

    observed: bool = _requires_compiled_graph(request=request)

    assert observed is test_case.expected_compiled_graph_required
