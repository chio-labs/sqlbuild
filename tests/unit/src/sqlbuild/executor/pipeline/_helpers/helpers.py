"""Helpers for executor pipeline helper tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    PlanOutput,
    ScenarioExecutionPlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
    SeedPlanEntry,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.scenario.constants import SCENARIO_LOCAL_JSONL_INVALID
from sqlbuild.executor.scenario.models import (
    ScenarioLocalSnapshotLoadResult,
    ScenarioSnapshotManifest,
)
from sqlbuild.observability import LifecycleEvent
from sqlbuild.spec.contracts.constants import DEFAULT_SEED_CSV_SETTINGS
from sqlbuild.spec.contracts.models import SeedCsvSettings
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    ScenarioLocalPipelineTestCase,
)


def lifecycle_events_with_prefix(
    *, events: list[LifecycleEvent], prefixes: tuple[str, ...]
) -> tuple[LifecycleEvent, ...]:
    return tuple(filter(lambda event: event.event_type.startswith(prefixes), events))


def lifecycle_order_with_prefix(*, order: list[str], prefixes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(filter(lambda item: item.startswith(prefixes), order))


def unprintable_audit_error() -> RuntimeError:
    value: MagicMock = MagicMock()
    value.__str__.side_effect = KeyboardInterrupt
    return RuntimeError(value)


def audit_entry(
    name: str,
    *,
    sql: str = "SELECT 1 WHERE FALSE",
    severity: AuditSeverity = AuditSeverity.ERROR,
) -> AuditPlanEntry:
    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=sql,
        unresolved_sql=sql,
        attachment_kind=AuditAttachmentKind.END,
        severity=severity,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
    )


def audit_result(name: str) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=name,
        attachment_kind=AuditAttachmentKind.END,
        severity=AuditSeverity.ERROR,
        outcome=AuditOutcome.PASS,
        row_count=0,
        executed_sql="SELECT 1 WHERE FALSE",
    )


class ScenarioPipelineTestAdapter(BaseAdapter):
    """Adapter that records pipeline connection lifecycle calls."""

    adapter_name: ClassVar[str] = "scenario-pipeline-test"

    def __init__(self) -> None:
        self.events: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        database: object = config.get("database", "")
        self.events.append(f"connect:{database}")
        return object()

    def _execute(self, connection: object, sql: str) -> object:
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
        Path(str(database)).touch()
        return object()


class SeedPipelineTestAdapter(BaseAdapter):
    """Adapter that records seed pipeline connection and load calls."""

    adapter_name: ClassVar[str] = "seed-pipeline-test"

    def __init__(self, *, barrier_targets: tuple[str, ...]) -> None:
        self.connections: list[object] = []
        self.closed_connections: list[object] = []
        self.loads: list[tuple[str, object]] = []
        self.barrier_targets: frozenset[str] = frozenset(barrier_targets)
        self.barrier = threading.Barrier(len(self.barrier_targets))

    def connect(self, config: dict[str, object]) -> object:
        del config
        connection: object = object()
        self.connections.append(connection)
        return connection

    def _execute(self, connection: object, sql: str) -> object:
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
        destination: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = DEFAULT_SEED_CSV_SETTINGS,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del file_path, columns, csv_settings, replace, infer_types, statement_recorder
        self.barrier.wait(timeout=1)
        self.loads.append((destination, connection))


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
        strategy: Callable[..., ScenarioExecutionPlan] = {
            self.planning_failure_name: self._raise_planning_error,
        }.get(scenario.name, build_scenario_pipeline_plan)
        return strategy(scenario=scenario)

    def _raise_planning_error(self, *, scenario: CompiledSqlScenario) -> ScenarioExecutionPlan:
        del scenario
        raise RuntimeError(self.error_message)


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
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=name,
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
        csv_settings=DEFAULT_SEED_CSV_SETTINGS,
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

    def load_snapshot_success(**_kwargs: object) -> ScenarioLocalSnapshotLoadResult:
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

    def load_snapshot_failure(**_kwargs: object) -> ScenarioLocalSnapshotLoadResult:
        raise ExecutorInputError(
            test_case.load_error_message or "",
            code=SCENARIO_LOCAL_JSONL_INVALID,
        )

    return {
        True: load_snapshot_success,
        False: load_snapshot_failure,
    }[test_case.load_error_message is None]
