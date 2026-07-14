"""dbt interop SQLBuild work models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class DbtSqlbuildWorkContext:
    """Shared execution context for one dbt interop SQLBuild work run."""

    plan_output: PlanOutput
    connection_config: dict[str, object]
    adapter: BaseAdapter
    adapter_name: str
    output_stream: TextIO
    use_color: bool
