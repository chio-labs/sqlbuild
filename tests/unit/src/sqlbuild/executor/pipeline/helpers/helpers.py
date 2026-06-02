"""Helpers for executor pipeline helper tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import (
    PlanOutput,
    ScenarioExecutionPlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
    SeedPlanEntry,
)
from sqlbuild.executor.scenario.models import (
    ScenarioLocalSnapshotLoadResult,
    ScenarioSnapshotManifest,
)
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.constants import SCENARIO_LOCAL_JSONL_INVALID
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings
from tests.unit.src.sqlbuild.executor.pipeline.helpers._test_types import (
    ScenarioLocalPipelineTestCase,
)


class ScenarioPipelineTestAdapter(BaseAdapter):
    """Adapter that records pipeline connection lifecycle calls."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        database: object = config.get("database", "")
        self.events.append(f"connect:{database}")
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        del connection
        self.events.append("close")


class ScenarioLocalPipelineTestAdapter(ScenarioPipelineTestAdapter):
    """Adapter that creates a local DuckDB placeholder file for pipeline tests."""

    def connect(self, config: dict[str, object]) -> object:
        database: object = config.get("database", "")
        self.events.append(f"connect:{database}")
        if database:
            Path(str(database)).touch()
        return object()


class SeedPipelineTestAdapter(BaseAdapter):
    """Adapter that records seed pipeline connection and load calls."""

    def __init__(self, *, barrier_targets: tuple[str, ...] = ()) -> None:
        self.connections: list[object] = []
        self.closed_connections: list[object] = []
        self.loads: list[tuple[str, object]] = []
        self.barrier_targets: frozenset[str] = frozenset(barrier_targets)
        self.barrier: threading.Barrier | None = None
        if self.barrier_targets:
            self.barrier = threading.Barrier(len(self.barrier_targets))

    def connect(self, config: dict[str, object]) -> object:
        del config
        connection: object = object()
        self.connections.append(connection)
        return connection

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        self.closed_connections.append(connection)

    def ensure_schema(
        self,
        connection: object,
        *,
        database: str | None,
        schema: str | None,
        statement_recorder: StatementRecorder | None = None,
    ) -> None:
        del connection, database, schema, statement_recorder

    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = default_seed_csv_settings,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del file_path, columns, csv_settings, replace, infer_types, statement_recorder
        if self.barrier is not None and target in self.barrier_targets:
            self.barrier.wait(timeout=1)
        self.loads.append((target, connection))


class ScenarioPipelinePlanBuilder:
    """Callable plan builder that can fail for one configured scenario."""

    def __init__(self, *, planning_failure_name: str, error_message: str) -> None:
        self.planning_failure_name: str = planning_failure_name
        self.error_message: str = error_message

    def __call__(
        self,
        *,
        scenario: CompiledSqlScenario,
        pipeline_result: CompilePipelineResult,
        adapter: ScenarioPipelineTestAdapter,
        project_name: str,
    ) -> ScenarioExecutionPlan:
        del pipeline_result, adapter, project_name
        if scenario.name == self.planning_failure_name:
            raise RuntimeError(self.error_message)
        return build_scenario_pipeline_plan(scenario=scenario)


def build_scenario_pipeline_result(*, scenario_names: tuple[str, ...]) -> CompilePipelineResult:
    """Build a minimal compile pipeline result containing SQL scenarios."""

    scenarios: tuple[CompiledSqlScenario, ...] = tuple(
        build_compiled_scenario(name=name) for name in scenario_names
    )
    return CompilePipelineResult(
        project=CompiledProject(
            run_id="scenario-test-run",
            effective_target_name=None,
            effective_connection={},
            effective_vars={},
            sql_scenarios=scenarios,
        ),
        plan_output=PlanOutput(),
    )


def build_seed_plan(*, seed_names: tuple[str, ...]) -> PlanOutput:
    """Build a minimal seed-only plan for pipeline tests."""

    return PlanOutput(
        seed_entries=tuple(build_seed_plan_entry(name=name) for name in seed_names),
    )


def build_seed_plan_entry(*, name: str) -> SeedPlanEntry:
    """Build one minimal seed plan entry for pipeline tests."""

    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        name=name,
        destination=CompiledRelationDestination(
            database=None,
            schema=None,
            name=name,
            qualified_name=name,
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
        csv_settings=default_seed_csv_settings,
    )


def build_compiled_scenario(*, name: str) -> CompiledSqlScenario:
    """Build a minimal compiled SQL scenario for pipeline tests."""

    return CompiledSqlScenario(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=name,
        ),
        name=name,
        scenario_file=DiscoveredSqlScenarioFile(
            file_path=Path(f"tests/scenarios/{name}.sql"),
            relative_path=Path(f"tests/scenarios/{name}.sql"),
            contents="SCENARIO ();",
            header_values={},
            sql_body="",
            name=name,
        ),
        sql_body="",
    )


def build_scenario_pipeline_plan(*, scenario: CompiledSqlScenario) -> ScenarioExecutionPlan:
    """Build a minimal scenario execution plan for pipeline tests."""

    return ScenarioExecutionPlan(
        key=scenario.key,
        name=scenario.name,
        graph_plan=ScenarioGraphPlan(key=scenario.key, name=scenario.name),
        relation_plan=ScenarioRelationPlan(
            scenario_name=scenario.name,
            relation_map=ScenarioRelationMap(
                scenario_name=scenario.name,
                hash_prefix="51b385aebe20",
            ),
        ),
    )


def local_snapshot_loader_for_test_case(
    test_case: ScenarioLocalPipelineTestCase,
) -> Callable[..., ScenarioLocalSnapshotLoadResult]:
    """Build a local snapshot loader stub for one pipeline test case."""

    def load_snapshot(**_kwargs: object) -> ScenarioLocalSnapshotLoadResult:
        if test_case.load_error_message is not None:
            raise ExecutorInputError(
                test_case.load_error_message,
                code=SCENARIO_LOCAL_JSONL_INVALID,
            )
        return ScenarioLocalSnapshotLoadResult(
            scenario_name="local_scenario",
            manifest=ScenarioSnapshotManifest(
                version=1,
                scenario_name="local_scenario",
                captured_at="2026-05-10T00:00:00Z",
                capture_adapter="duckdb",
                capture_dialect="duckdb",
                sqlbuild_version="0.0.0",
                input_fingerprint="fingerprint",
                total_rows=0,
                total_bytes=0,
            ),
        )

    return load_snapshot
