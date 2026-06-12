"""Tests for Python plan-entry display metadata."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.pipeline.helpers.python_plan_entries import build_python_plan_entries
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.python_nodes.helpers.run_lifecycle import build_python_sql_run_lifecycle_plan
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunSelection
from sqlbuild.compiler.python_nodes.types import PythonIdentityStatus
from tests.unit.src.sqlbuild.compiler.pipeline.helpers._test_types import (
    PythonPlanIdentityStatusTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.helpers.helpers import (
    build_previous_python_identity_map,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_orders_python_node_graph,
)

PYTHON_PLAN_IDENTITY_STATUS_TEST_CASES: list[PythonPlanIdentityStatusTestCase] = [
    PythonPlanIdentityStatusTestCase(
        description="marks missing previous identity as new",
        previous_version_hash=None,
        expected_status=PythonIdentityStatus.NEW,
    ),
    PythonPlanIdentityStatusTestCase(
        description="marks matching previous identity as unchanged",
        previous_version_hash="current",
        expected_status=PythonIdentityStatus.UNCHANGED,
    ),
    PythonPlanIdentityStatusTestCase(
        description="marks different previous identity as changed",
        previous_version_hash="previous",
        expected_status=PythonIdentityStatus.CHANGED,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_PLAN_IDENTITY_STATUS_TEST_CASES,
    ids=[case.description for case in PYTHON_PLAN_IDENTITY_STATUS_TEST_CASES],
)
def test_given_previous_python_identity_when_building_plan_entries_then_sets_status(
    test_case: PythonPlanIdentityStatusTestCase,
) -> None:
    graph: PythonNodeGraph = build_orders_python_node_graph()
    current_identity = graph.nodes_by_name["prepare_orders"].identity
    assert current_identity is not None
    current_version_hash: str = current_identity.version_hash
    previous_identities = build_previous_python_identity_map(
        previous_version_hash=test_case.previous_version_hash,
        current_version_hash=current_version_hash,
    )

    entries: tuple[PythonPlanEntry, ...] = build_python_plan_entries(
        lifecycle_plan=build_python_sql_run_lifecycle_plan(
            selection=PythonSqlRunSelection(
                sql_keys=frozenset(),
                python_node_names=frozenset({"prepare_orders"}),
            ),
            python_graph=graph,
        ),
        python_graph=graph,
        previous_identities=previous_identities,
    )

    assert entries[0].identity_status == test_case.expected_status
    assert entries[0].current_definition_json == current_identity.definition_json
    assert entries[0].current_metadata_json == current_identity.metadata_json
    expected_previous_payloads: bool = test_case.previous_version_hash is not None
    assert (entries[0].previous_definition_json is not None) is expected_previous_payloads
    assert (entries[0].previous_metadata_json is not None) is expected_previous_payloads
