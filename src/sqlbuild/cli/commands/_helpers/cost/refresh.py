"""Best-effort delayed Snowflake cost refresh."""

from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.constants import COST_HISTORY_SELECTOR, COST_LATEST_SELECTOR
from sqlbuild.cli.commands.models import CostCommandRequest
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostAwareAdapter, CostCapability, CostStatus
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


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
        summary: RunCostSummary = adapter.collect_run_cost(
            connection_config=connection_config,
            run_id=record.run_id,
            started_at=record.started_at,
            completed_at=record.completed_at,
            statement_ledger_path=(
                project_dir / "target" / "runs" / record.run_id / "statements.jsonl"
            ),
            usd_per_credit=record.cost.usd_per_credit,
            rate_source=record.cost.rate_source,
        )
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
