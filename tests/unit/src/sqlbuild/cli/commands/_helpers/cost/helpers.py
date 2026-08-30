from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands.models import BuildCostFinalization
from sqlbuild.spec.contracts.models import CostConfig


def build_cost_finalization(
    *,
    tmp_path: Path,
    adapter: object,
    output_stream: StringIO | Any,
    collect: bool = True,
    render: bool = True,
    had_executable_work: bool | None = True,
) -> BuildCostFinalization:
    now: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    return BuildCostFinalization(
        project_dir=tmp_path,
        adapter_name="snowflake",
        adapter=adapter,
        connection_config={},
        target_name="dev",
        target_database="RACING",
        run_id="run-1",
        build_status="success",
        started_at=now,
        completed_at=now,
        config=CostConfig(),
        output_stream=output_stream,
        use_color=False,
        collect=collect,
        render=render,
        had_executable_work=had_executable_work,
    )
