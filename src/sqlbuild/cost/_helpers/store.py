"""Atomic project-local run-cost persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from sqlbuild.cost.constants import LATEST_COST_RUN_SELECTOR, RUNNING_BUILD_STATUS
from sqlbuild.cost.exceptions import CostArtifactError
from sqlbuild.cost.models import CostRunRecord, ResourceCost, RunCostSummary
from sqlbuild.cost.types import CostStatus

_COST_ARTIFACT_VERSION: int = 1
_UNSAFE_RUN_ID_COMPONENTS: frozenset[str] = frozenset({".", ".."})
_RUN_ID_PATH_SEPARATORS: tuple[str, ...] = ("/", "\\")


class _Encoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, CostStatus):
            return o.value
        return super().default(o)


def write_cost_run(*, project_dir: Path, record: CostRunRecord) -> Path:
    run_dir: Path = _run_directory(project_dir=project_dir, run_id=record.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    destination: Path = run_dir / "run.json"
    temporary: Path = run_dir / ".run.json.tmp"
    temporary.write_text(
        json.dumps(asdict(record), cls=_Encoder, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    return destination


def format_cost_json(record: CostRunRecord) -> str:
    return json.dumps(cost_output_payload(record=record), cls=_Encoder, indent=2, sort_keys=True)


def format_cost_history_json(
    *, records: tuple[CostRunRecord, ...], matching_count: int | None = None
) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "command": "cost_history",
            "count": len(records),
            "matching_count": len(records) if matching_count is None else matching_count,
            "runs": [cost_output_payload(record=record) for record in records],
        },
        cls=_Encoder,
        indent=2,
        sort_keys=True,
    )


def read_cost_run(*, project_dir: Path, run_id: str) -> CostRunRecord | None:
    path: Path = _run_directory(project_dir=project_dir, run_id=run_id) / "run.json"
    if not path.is_file():
        return None
    record: CostRunRecord = _record_from_payload(json.loads(path.read_text(encoding="utf-8")))
    if record.run_id != run_id:
        raise CostArtifactError("cost run artifact run ID does not match its directory")
    return record


def list_cost_runs(*, project_dir: Path) -> tuple[CostRunRecord, ...]:
    root: Path = project_dir / "target" / "executions"
    if not root.is_dir():
        return ()
    records: list[CostRunRecord] = []
    for path in root.glob("*/run.json"):
        try:
            if not path.resolve().is_relative_to(root.resolve()):
                continue
            record: CostRunRecord = _record_from_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if record.run_id != path.parent.name:
                raise CostArtifactError("cost run artifact run ID does not match its directory")
            records.append(record)
        except (OSError, ValueError, TypeError, KeyError, InvalidOperation, json.JSONDecodeError):
            continue
    records.sort(key=lambda record: (record.completed_at, record.run_id), reverse=True)
    return tuple(records)


def resolve_cost_run(*, project_dir: Path, selector: str) -> CostRunRecord | None:
    records: tuple[CostRunRecord, ...] = list_cost_runs(project_dir=project_dir)
    if selector == LATEST_COST_RUN_SELECTOR:
        return next(
            (record for record in records if record.build_status != RUNNING_BUILD_STATUS),
            None,
        )
    matches: tuple[CostRunRecord, ...] = tuple(
        record for record in records if record.run_id.startswith(selector)
    )
    return matches[0] if len(matches) == 1 else None


def _record_from_payload(payload: object) -> CostRunRecord:
    if not isinstance(payload, dict):
        raise CostArtifactError("cost run artifact must be an object")
    payload_dict: dict[str, Any] = cast(dict[str, Any], payload)
    version: int = int(payload_dict["version"])
    if version != _COST_ARTIFACT_VERSION:
        raise CostArtifactError(f"unsupported cost run artifact version: {version}")
    run_id: str = str(payload_dict["run_id"])
    _validate_run_id(run_id=run_id)
    cost_payload: object = payload_dict["cost"]
    if not isinstance(cost_payload, dict):
        raise CostArtifactError("cost run artifact 'cost' must be an object")
    cost_payload_dict: dict[str, Any] = cast(dict[str, Any], cost_payload)
    resources_payload: object = cost_payload_dict.get("resources", [])
    if not isinstance(resources_payload, list):
        raise CostArtifactError("cost run artifact 'resources' must be a list")
    if not all(isinstance(item, dict) for item in resources_payload):
        raise CostArtifactError("cost run artifact resources must be objects")
    resources: tuple[ResourceCost, ...] = tuple(
        ResourceCost(
            resource_type=str(cast(dict[str, Any], item)["resource_type"]),
            resource_name=str(cast(dict[str, Any], item)["resource_name"]),
            warehouse_name=str(cast(dict[str, Any], item)["warehouse_name"]),
            warehouse_size=str(cast(dict[str, Any], item)["warehouse_size"]),
            warehouse_type=(
                None
                if cast(dict[str, Any], item).get("warehouse_type") is None
                else str(cast(dict[str, Any], item)["warehouse_type"])
            ),
            cluster_number=(
                None
                if cast(dict[str, Any], item).get("cluster_number") is None
                else int(cast(dict[str, Any], item)["cluster_number"])
            ),
            query_count=int(cast(dict[str, Any], item)["query_count"]),
            attributed_seconds=Decimal(str(cast(dict[str, Any], item)["attributed_seconds"])),
            bytes_scanned=int(cast(dict[str, Any], item)["bytes_scanned"]),
            estimated_compute_credits=Decimal(
                str(cast(dict[str, Any], item)["estimated_compute_credits"])
            ),
            estimated_usd=Decimal(str(cast(dict[str, Any], item)["estimated_usd"])),
        )
        for item in resources_payload
        if isinstance(item, dict)
    )
    started_at: datetime = _aware_datetime(value=payload_dict["started_at"], field="started_at")
    completed_at: datetime = _aware_datetime(
        value=payload_dict["completed_at"], field="completed_at"
    )
    had_executable_work_payload: object = payload_dict.get("had_executable_work")
    if had_executable_work_payload is not None and not isinstance(
        had_executable_work_payload, bool
    ):
        raise CostArtifactError("cost run artifact 'had_executable_work' must be a boolean")
    cost: RunCostSummary = RunCostSummary(
        status=CostStatus(str(cost_payload_dict["status"])),
        usd_per_credit=Decimal(str(cost_payload_dict["usd_per_credit"])),
        rate_source=str(cost_payload_dict["rate_source"]),
        resources=resources,
        query_count=int(cost_payload_dict.get("query_count", 0)),
        attributed_seconds=Decimal(str(cost_payload_dict.get("attributed_seconds", 0))),
        bytes_scanned=int(cost_payload_dict.get("bytes_scanned", 0)),
        estimated_compute_credits=Decimal(
            str(cost_payload_dict.get("estimated_compute_credits", 0))
        ),
        estimated_usd=Decimal(str(cost_payload_dict.get("estimated_usd", 0))),
        expected_statement_count=int(cost_payload_dict.get("expected_statement_count", 0)),
        observed_statement_count=int(cost_payload_dict.get("observed_statement_count", 0)),
        missing_statement_count=int(cost_payload_dict.get("missing_statement_count", 0)),
        skipped_statement_count=int(cost_payload_dict.get("skipped_statement_count", 0)),
        source=str(cost_payload_dict.get("source", "")),
        method=str(cost_payload_dict.get("method", "")),
        limitations=tuple(str(value) for value in cost_payload_dict.get("limitations", [])),
        message=(
            None if cost_payload_dict.get("message") is None else str(cost_payload_dict["message"])
        ),
    )
    return CostRunRecord(
        version=version,
        run_id=run_id,
        adapter_name=str(payload_dict["adapter_name"]),
        target_name=(
            None if payload_dict.get("target_name") is None else str(payload_dict["target_name"])
        ),
        build_status=str(payload_dict["build_status"]),
        started_at=started_at,
        completed_at=completed_at,
        cost=cost,
        had_executable_work=(
            None if had_executable_work_payload is None else had_executable_work_payload
        ),
    )


def _run_directory(*, project_dir: Path, run_id: str) -> Path:
    _validate_run_id(run_id=run_id)
    root: Path = project_dir / "target" / "executions"
    run_dir: Path = root / run_id
    if not run_dir.resolve().is_relative_to(root.resolve()):
        raise CostArtifactError("cost run path must remain under the project execution directory")
    return run_dir


def _validate_run_id(*, run_id: str) -> None:
    if (
        not run_id
        or run_id in _UNSAFE_RUN_ID_COMPONENTS
        or Path(run_id).name != run_id
        or any(separator in run_id for separator in _RUN_ID_PATH_SEPARATORS)
    ):
        raise CostArtifactError("cost run ID must be one path component")


def _aware_datetime(*, value: object, field: str) -> datetime:
    parsed: datetime = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CostArtifactError(f"cost run artifact '{field}' must include a timezone")
    return parsed


def cost_output_payload(*, record: CostRunRecord) -> dict[str, Any]:
    per_model: list[dict[str, object]] = [
        {
            "resource_type": resource.resource_type,
            "model": resource.resource_name,
            "warehouse": resource.warehouse_name,
            "warehouse_size": resource.warehouse_size,
            "warehouse_type": resource.warehouse_type,
            "cluster_number": resource.cluster_number,
            "query_count": resource.query_count,
            "attributed_seconds": str(resource.attributed_seconds),
            "bytes_scanned": resource.bytes_scanned,
            "attributed_compute_credits": str(resource.estimated_compute_credits),
            "estimated_usd": str(resource.estimated_usd),
        }
        for resource in record.cost.resources
    ]
    return {
        "schema_version": 1,
        "command": "cost",
        "run_id": record.run_id,
        "build_status": record.build_status,
        "started_at": record.started_at.isoformat(),
        "completed_at": record.completed_at.isoformat(),
        "adapter": record.adapter_name,
        "target": record.target_name,
        "had_executable_work": record.had_executable_work,
        "status": record.cost.status.value,
        "source": record.cost.source,
        "currency": "USD",
        "usd_per_credit": str(record.cost.usd_per_credit),
        "rate_source": record.cost.rate_source,
        "method": record.cost.method,
        "limitations": list(record.cost.limitations),
        "message": record.cost.message,
        "coverage": {
            "query_count": record.cost.query_count,
            "model_rows": len(record.cost.resources),
            "expected_statement_count": record.cost.expected_statement_count,
            "observed_statement_count": record.cost.observed_statement_count,
            "missing_statement_count": record.cost.missing_statement_count,
            "skipped_statement_count": record.cost.skipped_statement_count,
        },
        "per_model": per_model,
        "totals": {
            "query_count": record.cost.query_count,
            "attributed_seconds": str(record.cost.attributed_seconds),
            "bytes_scanned": record.cost.bytes_scanned,
            "attributed_compute_credits": str(record.cost.estimated_compute_credits),
            "estimated_usd": str(record.cost.estimated_usd),
        },
    }
