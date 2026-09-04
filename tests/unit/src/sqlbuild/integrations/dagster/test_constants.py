from __future__ import annotations

import pytest

from sqlbuild.compiler.dag.types import NodeKind
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.integrations.dagster.constants import (
    COMPLETED_EXECUTION_STATUS_EXCLUSIONS,
    COMPLETED_EXECUTION_STATUS_MEMBERS,
    COMPLETED_EXECUTION_STATUSES,
    COMPLETED_NODE_RESULT_STATUS_EXCLUSIONS,
    COMPLETED_NODE_RESULT_STATUS_MEMBERS,
    DAGSTER_ASSET_NODE_KIND_EXCLUSIONS,
    DAGSTER_ASSET_NODE_KIND_MEMBERS,
    DAGSTER_ASSET_NODE_KINDS,
    DAGSTER_DIRECT_KIND_NODE_KIND_EXCLUSIONS,
    DAGSTER_DIRECT_KIND_NODE_KIND_MEMBERS,
    DAGSTER_DIRECT_KIND_NODE_KINDS,
    DEFAULT_SELECTABLE_NODE_KIND_EXCLUSIONS,
    DEFAULT_SELECTABLE_NODE_KIND_MEMBERS,
    DEFAULT_SELECTABLE_NODE_KINDS,
    LOAD_SELECTABLE_NODE_KIND_EXCLUSIONS,
    LOAD_SELECTABLE_NODE_KIND_MEMBERS,
    LOAD_SELECTABLE_NODE_KINDS,
    MATERIALIZABLE_NODE_KIND_EXCLUSIONS,
    MATERIALIZABLE_NODE_KIND_MEMBERS,
    MATERIALIZABLE_NODE_KINDS,
    WARNING_CHECK_SEVERITY,
    WARNING_CHECK_SEVERITY_EXCLUSIONS,
    WARNING_CHECK_SEVERITY_MEMBERS,
)
from sqlbuild.python_nodes.types import PythonCheckSeverity
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterConstantGuardTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    assert_exhaustive_enum_partition,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterConstantGuardTestCase(
            description="all Dagster node-kind sets are exhaustive",
            expected_exhaustive=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_node_kind_enum_when_deriving_dagster_sets_then_every_kind_is_decided(
    test_case: DagsterConstantGuardTestCase,
) -> None:
    all_members: frozenset[NodeKind] = frozenset(NodeKind)
    derivations: tuple[tuple[frozenset[str], frozenset[NodeKind], frozenset[NodeKind]], ...] = (
        (
            DAGSTER_ASSET_NODE_KINDS,
            DAGSTER_ASSET_NODE_KIND_MEMBERS,
            DAGSTER_ASSET_NODE_KIND_EXCLUSIONS,
        ),
        (
            DAGSTER_DIRECT_KIND_NODE_KINDS,
            DAGSTER_DIRECT_KIND_NODE_KIND_MEMBERS,
            DAGSTER_DIRECT_KIND_NODE_KIND_EXCLUSIONS,
        ),
        (
            LOAD_SELECTABLE_NODE_KINDS,
            LOAD_SELECTABLE_NODE_KIND_MEMBERS,
            LOAD_SELECTABLE_NODE_KIND_EXCLUSIONS,
        ),
        (
            DEFAULT_SELECTABLE_NODE_KINDS,
            DEFAULT_SELECTABLE_NODE_KIND_MEMBERS,
            DEFAULT_SELECTABLE_NODE_KIND_EXCLUSIONS,
        ),
        (
            MATERIALIZABLE_NODE_KINDS,
            MATERIALIZABLE_NODE_KIND_MEMBERS,
            MATERIALIZABLE_NODE_KIND_EXCLUSIONS,
        ),
    )

    for derived_values, included, excluded in derivations:
        assert_exhaustive_enum_partition(
            all_members=all_members,
            included=included,
            excluded=excluded,
        )
        assert (included | excluded == all_members) is test_case.expected_exhaustive
        assert derived_values == frozenset(member.value for member in included)


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterConstantGuardTestCase(
            description="all terminal status sets are exhaustive",
            expected_exhaustive=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_status_enums_when_deriving_completed_statuses_then_every_status_is_decided(
    test_case: DagsterConstantGuardTestCase,
) -> None:
    assert_exhaustive_enum_partition(
        all_members=frozenset(ExecutionStatus),
        included=COMPLETED_EXECUTION_STATUS_MEMBERS,
        excluded=COMPLETED_EXECUTION_STATUS_EXCLUSIONS,
    )
    assert (
        COMPLETED_EXECUTION_STATUS_MEMBERS | COMPLETED_EXECUTION_STATUS_EXCLUSIONS
        == frozenset(ExecutionStatus)
    ) is test_case.expected_exhaustive
    assert_exhaustive_enum_partition(
        all_members=frozenset(NodeResultStatus),
        included=COMPLETED_NODE_RESULT_STATUS_MEMBERS,
        excluded=COMPLETED_NODE_RESULT_STATUS_EXCLUSIONS,
    )

    assert COMPLETED_EXECUTION_STATUSES == frozenset(
        status.value for status in COMPLETED_EXECUTION_STATUS_MEMBERS
    )
    assert COMPLETED_EXECUTION_STATUSES == frozenset(
        status.value for status in COMPLETED_NODE_RESULT_STATUS_MEMBERS
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterConstantGuardTestCase(
            description="all Python check severities are exhaustive",
            expected_exhaustive=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_check_severity_enum_when_deriving_warning_severity_then_every_severity_is_decided(
    test_case: DagsterConstantGuardTestCase,
) -> None:
    assert_exhaustive_enum_partition(
        all_members=frozenset(PythonCheckSeverity),
        included=WARNING_CHECK_SEVERITY_MEMBERS,
        excluded=WARNING_CHECK_SEVERITY_EXCLUSIONS,
    )
    assert (
        WARNING_CHECK_SEVERITY_MEMBERS | WARNING_CHECK_SEVERITY_EXCLUSIONS
        == frozenset(PythonCheckSeverity)
    ) is test_case.expected_exhaustive
    assert {WARNING_CHECK_SEVERITY} == {
        severity.value for severity in WARNING_CHECK_SEVERITY_MEMBERS
    }
