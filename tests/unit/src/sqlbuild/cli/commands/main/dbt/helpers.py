from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def build_empty_dbt_plan() -> DbtInteropPlan:
    """Build a minimal dbt interop plan for CLI output tests."""

    return build_dbt_interop_plan(
        command=DbtInteropCommand.PLAN,
        dbt_command_argv=("dbt", "ls"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
    )
