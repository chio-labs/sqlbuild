from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.planning.identities import (
    _reusable_execution_model_names,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    DirectModelVersionIdentities,
    PlannerChangeResults,
    PlannerIdentityContext,
)
from sqlbuild.compiler.planner.types import ChangeKind
from tests.unit.src.sqlbuild.compiler.planner._helpers.planning._test_types import (
    ReusableExecutionModelNamesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReusableExecutionModelNamesTestCase(
            description="different scope identity",
            execution_hash="execution-hash",
            stale_warning_hash="stale-warning-hash",
            query_change_tracking=True,
            expected_names=frozenset(),
        ),
        ReusableExecutionModelNamesTestCase(
            description="query tracking disabled",
            execution_hash="version-hash",
            stale_warning_hash="version-hash",
            query_change_tracking=False,
            expected_names=frozenset(),
        ),
        ReusableExecutionModelNamesTestCase(
            description="matching identity with query tracking",
            execution_hash="version-hash",
            stale_warning_hash="version-hash",
            query_change_tracking=True,
            expected_names=frozenset({"orders"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_execution_change_when_checking_reuse_then_requires_equivalent_semantics(
    test_case: ReusableExecutionModelNamesTestCase,
) -> None:
    execution_identities: DirectModelVersionIdentities = DirectModelVersionIdentities(
        function_local_hashes={},
        seed_version_hashes={},
        seed_metadata_jsons={},
        model_metadata_jsons={"orders": '{"materialized":"table"}'},
        model_local_hashes={"orders": "local-hash"},
        model_version_hashes={"orders": test_case.execution_hash},
    )
    stale_identities: DirectModelVersionIdentities = DirectModelVersionIdentities(
        function_local_hashes={},
        seed_version_hashes={},
        seed_metadata_jsons={},
        model_metadata_jsons={"orders": '{"materialized":"table"}'},
        model_local_hashes={"orders": "local-hash"},
        model_version_hashes={"orders": test_case.stale_warning_hash},
    )

    reusable_names: frozenset[str] = _reusable_execution_model_names(
        identities=PlannerIdentityContext(
            version_identities=execution_identities,
            stale_warning_identities=stale_identities,
        ),
        execution_changes=PlannerChangeResults(
            models={
                "orders": ChangeDetectionResult(
                    model_name="orders",
                    change_kind=ChangeKind.NO_CHANGE,
                )
            },
            functions={},
        ),
        query_change_tracking=test_case.query_change_tracking,
    )

    assert reusable_names == test_case.expected_names


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
