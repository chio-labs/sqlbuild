from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sqlbuild.cli.commands._helpers.cost.refresh import refresh_pending_cost_run
from sqlbuild.cli.commands.models import CostCommandRequest
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostCapability, CostStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.cost._test_types import (
    CostRefreshTestCase,
)
from tests.unit.src.sqlbuild.cost.helpers import build_cost_run_record


class _RefreshingCostAdapter:
    def cost_capability(self) -> CostCapability:
        return CostCapability.SNOWFLAKE_QUERY_HISTORY

    def collect_run_cost(self, **kwargs: Any) -> RunCostSummary:
        return RunCostSummary(
            status=CostStatus.COMPLETE,
            usd_per_credit=kwargs["usd_per_credit"],
            rate_source=kwargs["rate_source"],
            query_count=1,
            estimated_compute_credits=Decimal("0.01"),
            estimated_usd=Decimal("0.03"),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CostRefreshTestCase(
            description="latest selector refreshes pending run",
            selector="latest",
            expected_status=CostStatus.COMPLETE.value,
        ),
        CostRefreshTestCase(
            description="exact selector refreshes pending run",
            selector="run-pending",
            expected_status=CostStatus.COMPLETE.value,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_pending_run_when_showing_detail_then_persisted_summary_is_refreshed(
    test_case: CostRefreshTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    record: CostRunRecord = build_cost_run_record(run_id="run-pending", completed_at=now)
    RunCostStore.write(
        project_dir=tmp_path,
        record=replace(record, cost=replace(record.cost, status=CostStatus.PENDING)),
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.discover_project_inputs",
        lambda **kwargs: SimpleNamespace(project_config=object(), local_config=object()),
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.resolve_effective_adapter_name",
        lambda **kwargs: "snowflake",
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.resolve_adapter",
        lambda **kwargs: _RefreshingCostAdapter(),
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.resolve_project_connection_config",
        lambda **kwargs: {},
    )
    request: CostCommandRequest = CostCommandRequest(
        project_dir=tmp_path,
        selector=test_case.selector,
        no_color=True,
        limit=None,
        no_limit=False,
        sort=None,
        order=None,
        since=None,
        until=None,
        json_output=False,
        json_output_path=None,
    )

    refresh_pending_cost_run(request)

    refreshed: CostRunRecord | None = RunCostStore.read(project_dir=tmp_path, run_id="run-pending")
    assert refreshed is not None
    assert refreshed.cost.status.value == test_case.expected_status
    assert refreshed.cost.estimated_usd == Decimal("0.03")
