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
from sqlbuild.cost.constants import LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostCapability, CostStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.cost._test_types import (
    CostRefreshDegradationTestCase,
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


class _StaticCostAdapter:
    def __init__(self, summary: RunCostSummary) -> None:
        self.summary = summary

    def cost_capability(self) -> CostCapability:
        return CostCapability.SNOWFLAKE_QUERY_HISTORY

    def collect_run_cost(self, **kwargs: Any) -> RunCostSummary:
        del kwargs
        return self.summary


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
        CostRefreshTestCase(
            description="exact selector refreshes partial run",
            selector="run-pending",
            expected_status=CostStatus.COMPLETE.value,
            initial_status=CostStatus.PARTIAL,
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
        record=replace(record, cost=replace(record.cost, status=test_case.initial_status)),
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


@pytest.mark.parametrize(
    "test_case",
    [
        CostRefreshDegradationTestCase(
            description="collection failure does not replace useful partial",
            candidate_status=CostStatus.COLLECTION_FAILED,
            candidate_expected_statement_count=17,
            candidate_observed_statement_count=0,
            candidate_query_count=0,
            expected_status=CostStatus.PARTIAL,
            expected_observed_statement_count=17,
            expected_query_count=2,
        ),
        CostRefreshDegradationTestCase(
            description="missing ledger complete zero does not replace useful partial",
            candidate_status=CostStatus.COMPLETE,
            candidate_expected_statement_count=0,
            candidate_observed_statement_count=0,
            candidate_query_count=0,
            expected_status=CostStatus.PARTIAL,
            expected_observed_statement_count=17,
            expected_query_count=2,
        ),
        CostRefreshDegradationTestCase(
            description="lower partial coverage does not replace useful partial",
            candidate_status=CostStatus.PARTIAL,
            candidate_expected_statement_count=17,
            candidate_observed_statement_count=10,
            candidate_query_count=1,
            expected_status=CostStatus.PARTIAL,
            expected_observed_statement_count=17,
            expected_query_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_useful_partial_when_refresh_degrades_then_persisted_summary_is_preserved(
    test_case: CostRefreshDegradationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    record: CostRunRecord = build_cost_run_record(run_id="run-partial", completed_at=now)
    useful_partial: RunCostSummary = replace(
        record.cost,
        status=CostStatus.PARTIAL,
        expected_statement_count=17,
        observed_statement_count=17,
        query_count=2,
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=replace(record, cost=useful_partial),
    )
    candidate: RunCostSummary = RunCostSummary(
        status=test_case.candidate_status,
        usd_per_credit=record.cost.usd_per_credit,
        rate_source=record.cost.rate_source,
        expected_statement_count=test_case.candidate_expected_statement_count,
        observed_statement_count=test_case.candidate_observed_statement_count,
        query_count=test_case.candidate_query_count,
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
        lambda **kwargs: _StaticCostAdapter(candidate),
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.resolve_project_connection_config",
        lambda **kwargs: {},
    )
    request: CostCommandRequest = CostCommandRequest(
        project_dir=tmp_path,
        selector="run-partial",
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

    refreshed: CostRunRecord | None = RunCostStore.read(project_dir=tmp_path, run_id="run-partial")
    assert refreshed is not None
    assert refreshed.cost.status == test_case.expected_status
    assert refreshed.cost.observed_statement_count == test_case.expected_observed_statement_count
    assert refreshed.cost.query_count == test_case.expected_query_count
    assert refreshed.cost.estimated_usd == useful_partial.estimated_usd


@pytest.mark.parametrize(
    "test_case",
    [
        CostRefreshDegradationTestCase(
            description="consumed ledger failure is not replaced by false complete zero",
            candidate_status=CostStatus.COMPLETE,
            candidate_expected_statement_count=0,
            candidate_observed_statement_count=0,
            candidate_query_count=0,
            expected_status=CostStatus.PARTIAL,
            expected_observed_statement_count=0,
            expected_query_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_ledger_failure_when_refresh_has_no_coverage_then_failure_is_preserved(
    test_case: CostRefreshDegradationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    record: CostRunRecord = build_cost_run_record(run_id="run-ledger-failure", completed_at=now)
    failure_limitation: str = f"{LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX}OSError)."
    persisted_failure: RunCostSummary = RunCostSummary(
        status=CostStatus.PARTIAL,
        usd_per_credit=record.cost.usd_per_credit,
        rate_source=record.cost.rate_source,
        limitations=(failure_limitation,),
        message="Cost telemetry was only partially persisted.",
    )
    RunCostStore.write(
        project_dir=tmp_path,
        record=replace(record, cost=persisted_failure),
    )
    candidate: RunCostSummary = RunCostSummary(
        status=test_case.candidate_status,
        usd_per_credit=record.cost.usd_per_credit,
        rate_source=record.cost.rate_source,
        expected_statement_count=test_case.candidate_expected_statement_count,
        observed_statement_count=test_case.candidate_observed_statement_count,
        query_count=test_case.candidate_query_count,
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
        lambda **kwargs: _StaticCostAdapter(candidate),
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.cost.refresh.resolve_project_connection_config",
        lambda **kwargs: {},
    )
    request: CostCommandRequest = CostCommandRequest(
        project_dir=tmp_path,
        selector="run-ledger-failure",
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

    refreshed: CostRunRecord | None = RunCostStore.read(
        project_dir=tmp_path, run_id="run-ledger-failure"
    )
    assert refreshed is not None
    assert refreshed.cost.status == test_case.expected_status
    assert refreshed.cost.observed_statement_count == test_case.expected_observed_statement_count
    assert refreshed.cost.query_count == test_case.expected_query_count
    assert refreshed.cost.limitations == (failure_limitation,)
    assert refreshed.cost.message == persisted_failure.message
