"""dbt profile init entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.profile.init import (
    build_dbt_init_project,
    validate_dbt_init_project,
)
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult


def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
    """Create or render a minimal SQLBuild project from a dbt project."""

    return build_dbt_init_project(request=request)


def _validate_dbt_profile_init_request(*, request: DbtInitRequest) -> None:
    """Validate dbt profile init inputs without writing files or prompting."""

    validate_dbt_init_project(request=request)
