"""Tests for Python plan-entry display metadata."""

from __future__ import annotations

import base64
from datetime import datetime

import pytest

from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.pipeline._helpers.python_plan_entries import build_python_plan_entries
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.python_nodes._helpers.run_lifecycle import (
    build_python_sql_run_lifecycle_plan,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonNodeIdentity,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonIdentityStatus
from tests.unit.src.sqlbuild.compiler.fingerprints.main.helpers import (
    FakeFingerprintExecute,
    render_qualified_name,
    render_read_latest_sql,
)
from tests.unit.src.sqlbuild.compiler.pipeline._helpers._test_types import (
    PythonPlanIdentityStatusTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline._helpers.helpers import (
    build_previous_python_identity_map,
)
from tests.unit.src.sqlbuild.compiler.python_nodes._helpers.helpers import (
    build_orders_python_node_graph,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_previous_python_identity_when_building_plan_entries_then_sets_status(
    test_case: PythonPlanIdentityStatusTestCase,
) -> None:
    graph: PythonNodeGraph = build_orders_python_node_graph()
    current_identity: PythonNodeIdentity | None = graph.nodes_by_name["prepare_orders"].identity
    assert current_identity is not None
    current_version_hash: str = current_identity.version_hash
    previous_identities: dict[tuple[str, str], Fingerprint] = build_previous_python_identity_map(
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


@pytest.mark.parametrize(
    "test_case",
    [
        PythonPlanIdentityStatusTestCase(
            description="filtered warehouse read preserves unchanged direct Python identity",
            previous_version_hash="current",
            expected_status=PythonIdentityStatus.UNCHANGED,
        ),
        PythonPlanIdentityStatusTestCase(
            description="filtered warehouse read preserves changed direct Python identity",
            previous_version_hash="previous",
            expected_status=PythonIdentityStatus.CHANGED,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_filtered_warehouse_fingerprints_when_planning_python_then_sets_identity_status(
    test_case: PythonPlanIdentityStatusTestCase,
) -> None:
    graph: PythonNodeGraph = build_orders_python_node_graph()
    current_identity: PythonNodeIdentity | None = graph.nodes_by_name["prepare_orders"].identity
    assert current_identity is not None
    previous_version_hash: str = {
        "current": current_identity.version_hash,
    }.get(str(test_case.previous_version_hash), test_case.previous_version_hash or "")
    execute: FakeFingerprintExecute = FakeFingerprintExecute(
        rows=[
            (
                current_identity.node_type,
                current_identity.node_name,
                None,
                "main",
                None,
                "previous_run",
                current_identity.definition_hash,
                previous_version_hash,
                "schema_hash",
                base64.b64encode(current_identity.definition_json.encode()).decode(),
                base64.b64encode(current_identity.metadata_json.encode()).decode(),
                datetime(2026, 1, 1),
            )
        ]
    )

    fingerprints: FingerprintSet = read_latest_fingerprints(
        connection=object(),
        execute=execute,
        table_exists=True,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
        render_read_latest_sql=render_read_latest_sql,
        node_names=(),
        filtered_node_types=("model", "seed", "sql_udf"),
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
        previous_identities=fingerprints.fingerprints_by_identity,
    )

    assert "WHERE node_type NOT IN" in execute.executed_sql[0]
    assert entries[0].identity_status == test_case.expected_status
