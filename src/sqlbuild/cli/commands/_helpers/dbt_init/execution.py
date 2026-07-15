"""Execution phase for the dbt init command."""

from __future__ import annotations

from sqlbuild.cli.commands.models import DbtInitInvocation
from sqlbuild.integrations.dbt.main.profile.profile_init import run_dbt_profile_init
from sqlbuild.integrations.dbt.models import DbtInitResult


def execute_dbt_init(invocation: DbtInitInvocation) -> DbtInitResult:
    """Run dbt profile initialization."""

    return run_dbt_profile_init(request=invocation.request)
