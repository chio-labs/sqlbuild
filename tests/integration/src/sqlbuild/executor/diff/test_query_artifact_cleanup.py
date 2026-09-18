"""Integration coverage for query-diff artifact ownership and crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands._helpers.diff.execution import execute_query_diff
from sqlbuild.cli.commands.models import DiffCommandRequest, QueryDiffPreparation
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
    QueryArtifactCleanupFailureTestCase,
    QueryArtifactCleanupTestCase,
)


class _CleanupFailingDuckDbAdapter(DuckDbAdapter):
    def drop(
        self,
        *,
        connection: Any,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, destination, if_exists, statement_recorder
        raise AdapterUserError("simulated query artifact cleanup failure")


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


@pytest.mark.parametrize(
    "test_case",
    [
        QueryArtifactCleanupFailureTestCase(
            description="current-run artifacts remain after mandatory cleanup fails",
            run_id="20260918T142303Z_c1d2e3f4a5b6",
            expected_error="simulated query artifact cleanup failure",
            expected_artifact_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_current_artifact_cleanup_failure_when_executing_query_diff_then_failure_is_mandatory(
    test_case: QueryArtifactCleanupFailureTestCase,
    tmp_path: Path,
) -> None:
    database_path: Path = tmp_path / "query_diff.duckdb"
    adapter: DuckDbAdapter = _CleanupFailingDuckDbAdapter()
    request: DiffCommandRequest = DiffCommandRequest(
        project_dir=None,
        no_color=True,
        no_sql_validation=False,
        from_name=None,
        to_name=None,
        full=False,
        schema_only=False,
        bounded=None,
        unique_key_override=("order_id",),
    )
    preparation: QueryDiffPreparation = QueryDiffPreparation(
        adapter=adapter,
        connection_config={"database": str(database_path)},
        left_sql="SELECT 1 AS order_id",
        right_sql="SELECT 1 AS order_id",
        left_label="baseline",
        right_label="candidate",
        selected_target="dev",
        database=None,
        schema="main",
        run_id=test_case.run_id,
        artifact_ttl="24h",
        effective_max_column_examples=3,
        effective_max_row_only_examples=3,
    )

    with pytest.raises(AdapterUserError, match=test_case.expected_error):
        execute_query_diff(request=request, preparation=preparation)

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(database_path))
    try:
        artifact_count_row: tuple[int] | None = connection.execute(
            "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name LIKE '__sqlbuild_query_diff_%'"
        ).fetchone()
        assert artifact_count_row == (test_case.expected_artifact_count,)
    finally:
        connection.close()
