"""CLI run-cost history and drill-down."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands._helpers.cost.output import (
    format_cost_breakdown,
    format_cost_history,
)
from sqlbuild.cli.commands.constants import (
    COST_DEFAULT_DETAIL_SORT,
    COST_DEFAULT_HISTORY_LIMIT,
    COST_DEFAULT_HISTORY_SORT,
    COST_DESCENDING_ORDER,
    COST_HISTORY_SELECTOR,
    COST_LATEST_SELECTOR,
    ISO_DATE_LENGTH,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import CostCommandRequest
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.models import CostRunRecord, ResourceCost
from sqlbuild.cost.types import CostStatus
from sqlbuild.cursor_algebra.constants import MINUTE_TO_DAY_DURATION_UNITS
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.presentation.main.supports_color import supports_color

_HISTORY_SORT_FIELDS: frozenset[str] = frozenset(
    {"completed", "cost", "credits", "duration", "models", "status"}
)
_BREAKDOWN_SORT_FIELDS: frozenset[str] = frozenset(
    {"cost", "credits", "busy", "scanned", "model", "warehouse"}
)
_MISSING_METRIC_STATUSES: frozenset[CostStatus] = frozenset(
    {
        CostStatus.PENDING,
        CostStatus.PARTIAL,
        CostStatus.UNAVAILABLE,
        CostStatus.COLLECTION_FAILED,
    }
)
_HISTORY_METRIC_SORT_FIELDS: frozenset[str] = frozenset({"cost", "credits"})
_ZERO_DAY_DURATION: str = "0d"


def run_cost_command(request: CostCommandRequest) -> int:
    """Render persisted cost history or one run breakdown."""

    project_dir: Path = request.project_dir if request.project_dir is not None else Path.cwd()
    _validate_limit(request=request)
    if request.selector == COST_HISTORY_SELECTOR:
        return _run_history(request=request, project_dir=project_dir)
    return _run_detail(request=request, project_dir=project_dir)


def _run_history(*, request: CostCommandRequest, project_dir: Path) -> int:
    sort_field: str = request.sort or COST_DEFAULT_HISTORY_SORT
    order: str = request.order or COST_DESCENDING_ORDER
    if sort_field not in _HISTORY_SORT_FIELDS:
        raise CliUserError(
            f"cost history --sort must be one of: {', '.join(sorted(_HISTORY_SORT_FIELDS))}",
            code="C701",
        )
    since: datetime | None = _parse_since_bound(value=request.since)
    until: datetime | None = _parse_bound(value=request.until, label="--until", end_of_day=True)
    if since is not None and until is not None and since > until:
        raise CliUserError("cost --since must not be after --until", code="C711")
    until_is_date: bool = request.until is not None and len(request.until) == ISO_DATE_LENGTH
    matching_records: tuple[CostRunRecord, ...] = tuple(
        record
        for record in RunCostStore.list(project_dir=project_dir)
        if (since is None or record.completed_at >= since)
        and (
            until is None
            or (record.completed_at < until if until_is_date else record.completed_at <= until)
        )
    )
    records: tuple[CostRunRecord, ...] = _sort_history_records(
        records=matching_records,
        field=sort_field,
        descending=order == COST_DESCENDING_ORDER,
    )
    limit: int | None = (
        None
        if request.no_limit
        else COST_DEFAULT_HISTORY_LIMIT
        if request.limit is None
        else request.limit
    )
    if limit is not None:
        records = records[:limit]
    payload: str = RunCostStore.format_history_json(
        records=records, matching_count=len(matching_records)
    )
    _write_json_output(payload=payload, path=request.json_output_path)
    if request.json_output:
        sys.stdout.write(payload + "\n")
    else:
        sys.stdout.write(
            format_cost_history(
                records=records,
                matching_count=len(matching_records),
                use_color=(not request.no_color) and supports_color(),
            )
            + "\n"
        )
    return 0


def _run_detail(*, request: CostCommandRequest, project_dir: Path) -> int:
    if request.since is not None or request.until is not None:
        raise CliUserError("--since and --until are only valid for cost history", code="C702")
    sort_field: str = request.sort or COST_DEFAULT_DETAIL_SORT
    order: str = request.order or COST_DESCENDING_ORDER
    if sort_field not in _BREAKDOWN_SORT_FIELDS:
        raise CliUserError(
            f"cost --sort must be one of: {', '.join(sorted(_BREAKDOWN_SORT_FIELDS))}",
            code="C703",
        )
    record: CostRunRecord = _resolve_run(project_dir=project_dir, selector=request.selector)
    resources: tuple[ResourceCost, ...] = tuple(
        sorted(
            record.cost.resources,
            key=lambda resource: (
                _resource_sort_value(resource=resource, field=sort_field),
                resource.resource_name,
                resource.warehouse_name,
            ),
            reverse=order == COST_DESCENDING_ORDER,
        )
    )
    record = replace(record, cost=replace(record.cost, resources=resources))
    limit: int | None = None if request.no_limit else request.limit
    json_record: CostRunRecord = (
        record
        if limit is None
        else replace(record, cost=replace(record.cost, resources=resources[:limit]))
    )
    payload: str = RunCostStore.format_json(json_record)
    _write_json_output(payload=payload, path=request.json_output_path)
    if request.json_output:
        sys.stdout.write(payload + "\n")
    else:
        sys.stdout.write(
            format_cost_breakdown(
                record=record,
                use_color=(not request.no_color) and supports_color(),
                limit=limit,
            )
            + "\n"
        )
    return 0


def _resolve_run(*, project_dir: Path, selector: str) -> CostRunRecord:
    records: tuple[CostRunRecord, ...] = RunCostStore.list(project_dir=project_dir)
    if selector == COST_LATEST_SELECTOR:
        latest: CostRunRecord | None = RunCostStore.resolve(
            project_dir=project_dir,
            selector=selector,
        )
        if latest is not None:
            return latest
        raise CliUserError("No persisted SQLBuild cost runs were found", code="C704")
    exact: tuple[CostRunRecord, ...] = tuple(
        record for record in records if record.run_id == selector
    )
    if exact:
        return exact[0]
    matches: tuple[CostRunRecord, ...] = tuple(
        record for record in records if record.run_id.startswith(selector)
    )
    if not matches:
        raise CliUserError(f"No cost run matches '{selector}'", code="C705")
    if len(matches) > 1:
        matching_ids: str = ", ".join(record.run_id for record in matches)
        raise CliUserError(
            f"Cost run prefix '{selector}' is ambiguous; matches: {matching_ids}",
            code="C706",
        )
    return matches[0]


def _parse_bound(*, value: str | None, label: str, end_of_day: bool) -> datetime | None:
    if value is None:
        return None
    try:
        if len(value) == ISO_DATE_LENGTH:
            parsed_date: date = date.fromisoformat(value)
            start: datetime = datetime.combine(parsed_date, time.min, tzinfo=UTC)
            return start + timedelta(days=1) if end_of_day else start
        parsed: datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CliUserError(f"cost {label} must be an ISO date or datetime", code="C707") from error
    if parsed.tzinfo is None:
        raise CliUserError(f"cost {label} datetime must include a timezone", code="C708")
    return parsed.astimezone(UTC)


def _parse_since_bound(*, value: str | None) -> datetime | None:
    if value is None:
        return None
    if value == _ZERO_DAY_DURATION:
        return datetime.now(UTC)
    duration: Duration | None = Duration.parse(value)
    if duration is None:
        return _parse_bound(value=value, label="--since", end_of_day=False)
    if not duration.is_single_unit_in(MINUTE_TO_DAY_DURATION_UNITS):
        raise CliUserError("cost --since relative duration must use one of: d, h, m", code="C707")
    return datetime.now(UTC) - timedelta(seconds=duration.fixed_seconds)


def _sort_history_records(
    *, records: tuple[CostRunRecord, ...], field: str, descending: bool
) -> tuple[CostRunRecord, ...]:
    if field not in _HISTORY_METRIC_SORT_FIELDS:
        return _sort_history_partition(
            records=records,
            field=field,
            descending=descending,
        )
    available: tuple[CostRunRecord, ...] = tuple(
        record for record in records if record.cost.status not in _MISSING_METRIC_STATUSES
    )
    missing: tuple[CostRunRecord, ...] = tuple(
        record for record in records if record.cost.status in _MISSING_METRIC_STATUSES
    )
    sorted_available: tuple[CostRunRecord, ...] = _sort_history_partition(
        records=available,
        field=field,
        descending=descending,
    )
    sorted_missing: tuple[CostRunRecord, ...] = tuple(
        sorted(
            sorted(missing, key=lambda record: record.run_id),
            key=lambda record: record.completed_at,
            reverse=True,
        )
    )
    return (*sorted_available, *sorted_missing)


def _sort_history_partition(
    *, records: tuple[CostRunRecord, ...], field: str, descending: bool
) -> tuple[CostRunRecord, ...]:
    by_run_id: list[CostRunRecord] = sorted(records, key=lambda record: record.run_id)
    by_completion: list[CostRunRecord] = sorted(
        by_run_id,
        key=lambda record: record.completed_at,
        reverse=True,
    )
    return tuple(
        sorted(
            by_completion,
            key=lambda record: _history_sort_value(record=record, field=field),
            reverse=descending,
        )
    )


def _history_sort_value(*, record: CostRunRecord, field: str) -> Any:
    values: dict[str, Any] = {
        "completed": record.completed_at,
        "cost": record.cost.estimated_usd,
        "credits": record.cost.estimated_compute_credits,
        "duration": record.completed_at - record.started_at,
        "models": len(record.cost.resources),
        "status": record.cost.status.value,
    }
    return values[field]


def _resource_sort_value(*, resource: ResourceCost, field: str) -> Any:
    values: dict[str, Any] = {
        "cost": resource.estimated_usd,
        "credits": resource.estimated_compute_credits,
        "busy": resource.attributed_seconds,
        "scanned": resource.bytes_scanned,
        "model": resource.resource_name,
        "warehouse": resource.warehouse_name,
    }
    return values[field]


def _validate_limit(*, request: CostCommandRequest) -> None:
    if request.limit is not None and request.limit < 0:
        raise CliUserError("cost --limit must be non-negative", code="C709")
    if request.no_limit and request.limit is not None:
        raise CliUserError("cost --limit and --no-limit cannot be combined", code="C710")


def _write_json_output(*, payload: str, path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")
