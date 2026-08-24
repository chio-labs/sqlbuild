"""Project-local run-cost store."""

from pathlib import Path

from sqlbuild.cost._helpers.store import (
    cost_output_payload,
    format_cost_history_json,
    format_cost_json,
    list_cost_runs,
    read_cost_run,
    resolve_cost_run,
    write_cost_run,
)
from sqlbuild.cost.models import CostRunRecord


class RunCostStore:
    @staticmethod
    def write(*, project_dir: Path, record: CostRunRecord) -> Path:
        return write_cost_run(project_dir=project_dir, record=record)

    @staticmethod
    def read(*, project_dir: Path, run_id: str) -> CostRunRecord | None:
        return read_cost_run(project_dir=project_dir, run_id=run_id)

    @staticmethod
    def list(*, project_dir: Path) -> tuple[CostRunRecord, ...]:
        return list_cost_runs(project_dir=project_dir)

    @staticmethod
    def resolve(*, project_dir: Path, selector: str) -> CostRunRecord | None:
        return resolve_cost_run(project_dir=project_dir, selector=selector)

    @staticmethod
    def format_json(record: CostRunRecord) -> str:
        return format_cost_json(record)

    @staticmethod
    def format_history_json(
        *, records: tuple[CostRunRecord, ...], matching_count: int | None = None
    ) -> str:
        return format_cost_history_json(records=records, matching_count=matching_count)

    @staticmethod
    def output_payload(*, record: CostRunRecord) -> dict[str, object]:
        return cost_output_payload(record=record)
