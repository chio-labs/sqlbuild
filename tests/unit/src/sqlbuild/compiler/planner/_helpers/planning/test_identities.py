from __future__ import annotations

from types import SimpleNamespace

import pytest

import sqlbuild._native as native_module
from sqlbuild._native import (
    ChangeDetectionResult,
    ChangeKind,
    DirectModelVersionIdentities,
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerScopeResolution,
    WarehouseSnapshot,
    detect_stale_warning_changes,
)
from sqlbuild.compiler.planner.models import (
    PlannerScope,
)
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
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(native_module, "detect_model_changes_in_scope", lambda **_: {})
    stale_scope: PlannerScope = PlannerScope(
        upstream_deps={},
        downstream_deps={},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset(),
        execution_order=(),
    )

    reused: PlannerChangeResults = detect_stale_warning_changes(
        project=SimpleNamespace(
            settings=SimpleNamespace(query_change_tracking=test_case.query_change_tracking)
        ),
        scopes=PlannerScopeResolution(
            selected_scope=stale_scope,
            stale_warning_scope=stale_scope,
            inspection_scope=stale_scope,
        ),
        snapshot=WarehouseSnapshot(),
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
    )

    assert frozenset(reused.models) == test_case.expected_names


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
