"""Integration coverage for query-diff artifact ownership and crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_QUERY_DIFF_ARTIFACT
from sqlbuild.executor.diff.classes.query_artifact_lifecycle import QueryDiffArtifactLifecycle
from sqlbuild.executor.diff.models import QueryDiffArtifact
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorDirectModeSettings,
    JanitorExecutionResult,
    JanitorPlan,
)
from tests.integration.src.sqlbuild.executor.diff._test_types import (
    QueryArtifactCleanupTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryArtifactCleanupTestCase(
            description="owned expiry and untracked protection",
            expected_fingerprint_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_expired_owned_and_untracked_artifacts_when_janitor_runs_then_only_owned_artifact_is_deleted(
    test_case: QueryArtifactCleanupTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    owned: QueryDiffArtifact = QueryDiffArtifactLifecycle.build(
        adapter=adapter,
        run_id="20260918T142301Z_a1b2c3d4e5f6",
        side="left",
        database=None,
        schema="main",
    )
    untracked: QueryDiffArtifact = QueryDiffArtifactLifecycle.build(
        adapter=adapter,
        run_id="20260918T142302Z_b1c2d3e4f5a6",
        side="right",
        database=None,
        schema="main",
    )
    try:
        QueryDiffArtifactLifecycle.materialize(
            adapter=adapter,
            connection=connection,
            artifact=owned,
            sql="SELECT 1 AS order_id",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        normalized_owned_name: str = owned.name.lower()
        connection.execute(f"ALTER TABLE {owned.relation} RENAME TO {normalized_owned_name}")
        connection.execute(f"CREATE TABLE {untracked.relation} AS SELECT 2 AS order_id")
        project: CompiledProject = CompiledProject(
            run_id="run-1",
            effective_target_name="dev",
            effective_connection={},
            effective_vars={},
            effective_target_schema="main",
        )

        plan: JanitorPlan = build_janitor_plan(
            project=project,
            adapter=adapter,
            connection=connection,
            retention_days=30,
            direct_settings=JanitorDirectModeSettings(enabled=True),
        )

        assert tuple(candidate.key.name for candidate in plan.query_diff_artifact_candidates) == (
            normalized_owned_name,
        )
        assert any(
            skipped.key.name == untracked.name
            and "lacks matching ownership evidence" in skipped.reason
            for skipped in plan.skipped_relations
        )

        result: JanitorExecutionResult = execute_janitor_plan(
            plan=plan,
            adapter=adapter,
            connection=connection,
        )

        assert tuple(candidate.key.name for candidate in result.deleted_query_diff_artifacts) == (
            normalized_owned_name,
        )
        assert not adapter.relation_exists(
            connection=connection,
            database=None,
            schema="main",
            name=normalized_owned_name,
        )
        assert adapter.relation_exists(
            connection=connection,
            database=None,
            schema="main",
            name=untracked.name,
        )
        fingerprint_row: tuple[int] | None = connection.execute(
            "SELECT COUNT(*) FROM main._sqlbuild_fingerprints WHERE node_type = ?",
            [NODE_TYPE_QUERY_DIFF_ARTIFACT],
        ).fetchone()
        assert fingerprint_row == (test_case.expected_fingerprint_count,)
    finally:
        connection.close()
