"""dbt profile init entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.profile_init import build_dbt_init_project
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult


def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
    """Create or render a minimal SQLBuild project from a dbt project."""

    return build_dbt_init_project(request=request)
