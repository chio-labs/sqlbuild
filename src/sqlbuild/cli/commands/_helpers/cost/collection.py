"""Nonfatal automatic cost collection after a native build."""

from __future__ import annotations

import logging
from typing import TextIO

from sqlbuild.cli.commands._helpers.cost.output import format_cost_breakdown
from sqlbuild.cli.commands.models import BuildCostFinalization
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.constants import DEFAULT_RATE_SOURCE
from sqlbuild.cost.models import CostRunRecord, RunCostSummary
from sqlbuild.cost.types import CostAwareAdapter, CostCapability, CostStatus
from sqlbuild.spec.contracts.models import CostConfig

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cost")


def finalize_build_cost(finalization: BuildCostFinalization) -> CostRunRecord | None:
    """Collect, persist, and render without allowing cost failures to affect a build."""

    if not isinstance(finalization.adapter, CostAwareAdapter):
        return None
    config: CostConfig = finalization.config
    rate_source: str = DEFAULT_RATE_SOURCE if config.usd_per_credit_is_default else "configured"
    try:
        capability: CostCapability = finalization.adapter.cost_capability()
    except BaseException as error:
        return _persist_collection_failure(
            finalization=finalization,
            rate_source=rate_source,
            stage="capability detection",
            error=error,
        )
    if capability == CostCapability.NONE:
        return None
    if finalization.collect:
        try:
            summary: RunCostSummary = finalization.adapter.collect_run_cost(
                connection_config=finalization.connection_config,
                run_id=finalization.run_id,
                started_at=finalization.started_at,
                completed_at=finalization.completed_at,
                statement_ledger_path=(
                    finalization.project_dir
                    / "target"
                    / "runs"
                    / finalization.run_id
                    / "statements.jsonl"
                ),
                usd_per_credit=config.usd_per_credit,
                rate_source=rate_source,
            )
        except BaseException as error:
            return _persist_collection_failure(
                finalization=finalization,
                rate_source=rate_source,
                stage="collection",
                error=error,
            )
    else:
        summary = RunCostSummary(
            status=finalization.cost_status,
            usd_per_credit=config.usd_per_credit,
            rate_source=rate_source,
            message=finalization.cost_message,
        )
    record: CostRunRecord = CostRunRecord(
        run_id=finalization.run_id,
        adapter_name=finalization.adapter_name,
        target_name=finalization.target_name,
        build_status=finalization.build_status,
        started_at=finalization.started_at,
        completed_at=finalization.completed_at,
        cost=summary,
        had_executable_work=finalization.had_executable_work,
    )
    try:
        RunCostStore.write(project_dir=finalization.project_dir, record=record)
    except BaseException as error:
        _LOGGER.exception("automatic run-cost persistence failed")
        _write_warning(
            output_stream=finalization.output_stream,
            message=(
                "Cost telemetry failed during artifact persistence "
                f"({type(error).__name__}); build result unchanged."
            ),
        )
    if not finalization.render:
        return record
    _render_build_cost(
        record=record,
        output_stream=finalization.output_stream,
        use_color=finalization.use_color,
    )
    return record


def render_build_cost(
    *, record: CostRunRecord | None, output_stream: TextIO, use_color: bool
) -> None:
    """Render a previously finalized record without affecting native build output."""

    if record is None:
        return
    _render_build_cost(record=record, output_stream=output_stream, use_color=use_color)


def _render_build_cost(*, record: CostRunRecord, output_stream: TextIO, use_color: bool) -> None:
    try:
        output_stream.write(
            "\n"
            + format_cost_breakdown(
                record=record,
                use_color=use_color,
                limit=5,
                show_run_id=False,
            )
            + "\n"
        )
        output_stream.flush()
    except Exception as error:
        _LOGGER.exception("automatic run-cost output failed")
        _write_warning(
            output_stream=output_stream,
            message=(
                "Cost telemetry failed during output rendering "
                f"({type(error).__name__}); build result unchanged."
            ),
        )


def _write_warning(*, output_stream: TextIO, message: str) -> None:
    try:
        output_stream.write(f"\nWARNING: {message}\n")
        output_stream.flush()
    except BaseException:
        _LOGGER.exception("automatic run-cost warning output failed")


def _persist_collection_failure(
    *,
    finalization: BuildCostFinalization,
    rate_source: str,
    stage: str,
    error: BaseException,
) -> CostRunRecord:
    _LOGGER.exception("automatic run-cost %s failed", stage)
    error_type: str = type(error).__name__
    _write_warning(
        output_stream=finalization.output_stream,
        message=(f"Cost telemetry failed during {stage} ({error_type}); build result unchanged."),
    )
    record: CostRunRecord = CostRunRecord(
        run_id=finalization.run_id,
        adapter_name=finalization.adapter_name,
        target_name=finalization.target_name,
        build_status=finalization.build_status,
        started_at=finalization.started_at,
        completed_at=finalization.completed_at,
        cost=RunCostSummary(
            status=CostStatus.COLLECTION_FAILED,
            usd_per_credit=finalization.config.usd_per_credit,
            rate_source=rate_source,
            message=f"Cost telemetry failed during {stage} ({error_type}).",
        ),
        had_executable_work=finalization.had_executable_work,
    )
    try:
        RunCostStore.write(project_dir=finalization.project_dir, record=record)
    except BaseException as persistence_error:
        _LOGGER.exception("automatic run-cost failure artifact persistence failed")
        _write_warning(
            output_stream=finalization.output_stream,
            message=(
                "Cost telemetry failed during failure artifact persistence "
                f"({type(persistence_error).__name__}); build result unchanged."
            ),
        )
    return record
