"""Best-effort delayed Snowflake cost refresh."""

from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.constants import COST_HISTORY_SELECTOR, COST_LATEST_SELECTOR
from sqlbuild.cli.commands.models import CostCommandRequest
from sqlbuild.compiler.compile.main.effective_target import build_effective_target_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.constants import LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostAwareAdapter, CostCapability, CostStatus
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import TargetConfig

_REFRESH_STATUS_RANK: dict[CostStatus, int] = {
    CostStatus.COLLECTION_FAILED: 0,
    CostStatus.UNAVAILABLE: 0,
    CostStatus.PENDING: 1,
    CostStatus.PARTIAL: 2,
    CostStatus.COMPLETE: 3,
}


def refresh_pending_cost_run(request: CostCommandRequest) -> None:
    """Refresh one delayed record without making lookup depend on Snowflake availability."""

    if request.selector == COST_HISTORY_SELECTOR:
        return
    project_dir: Path = request.project_dir if request.project_dir is not None else Path.cwd()
    try:
        record: CostRunRecord | None = _resolve_refresh_record(
            project_dir=project_dir,
            selector=request.selector,
        )
        if record is None or record.cost.status not in {
            CostStatus.PENDING,
            CostStatus.PARTIAL,
        }:
            return
        discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
        target_config: TargetConfig | None = build_effective_target_config(
            discovered_inputs=discovered,
            selected_target=record.target_name,
        )
        adapter_name: str = resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        )
        adapter: object = resolve_adapter(adapter_name=adapter_name, project_dir=project_dir)
        if not isinstance(adapter, CostAwareAdapter):
            return
        if adapter.cost_capability() == CostCapability.NONE:
            return
        connection_config: dict[str, object] = resolve_project_connection_config(
            discovered_inputs=discovered,
            project_dir=project_dir,
            selected_target=record.target_name,
        )
        connection_database: object | None = connection_config.get("database")
        target_database: str | None = (
            target_config.database
            if target_config is not None and target_config.database is not None
            else (None if connection_database is None else str(connection_database))
        )
        summary: RunCostSummary = adapter.collect_run_cost(
            connection_config=connection_config,
            target_database=target_database,
            run_id=record.run_id,
            started_at=record.started_at,
            completed_at=record.completed_at,
            statement_ledger_path=(
                project_dir / "target" / "executions" / record.run_id / "statements.jsonl"
            ),
            usd_per_credit=record.cost.usd_per_credit,
            rate_source=record.cost.rate_source,
        )
        if _is_non_destructive_refresh(current=record.cost, candidate=summary):
            RunCostStore.write(project_dir=project_dir, record=replace(record, cost=summary))
    except BaseException:
        return


def _resolve_refresh_record(*, project_dir: Path, selector: str) -> CostRunRecord | None:
    if selector == COST_LATEST_SELECTOR:
        return RunCostStore.resolve(project_dir=project_dir, selector=selector)
    exact: CostRunRecord | None = RunCostStore.read(project_dir=project_dir, run_id=selector)
    if exact is not None:
        return exact
    return RunCostStore.resolve(project_dir=project_dir, selector=selector)


def _is_non_destructive_refresh(*, current: RunCostSummary, candidate: RunCostSummary) -> bool:
    """Accept refreshed telemetry only when persisted coverage cannot regress."""

    if _REFRESH_STATUS_RANK[candidate.status] < _REFRESH_STATUS_RANK[current.status]:
        return False
    if _has_ledger_persistence_failure(summary=current) and not _has_coverage_gain(
        current=current,
        candidate=candidate,
    ):
        return False
    return (
        candidate.expected_statement_count >= current.expected_statement_count
        and candidate.observed_statement_count >= current.observed_statement_count
        and candidate.query_count >= current.query_count
    )


def _has_ledger_persistence_failure(*, summary: RunCostSummary) -> bool:
    return any(
        limitation.startswith(LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX)
        for limitation in summary.limitations
    )


def _has_coverage_gain(*, current: RunCostSummary, candidate: RunCostSummary) -> bool:
    return (
        candidate.expected_statement_count > current.expected_statement_count
        or candidate.observed_statement_count > current.observed_statement_count
        or candidate.query_count > current.query_count
    )
