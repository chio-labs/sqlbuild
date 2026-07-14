"""Resolve SQLBuild test actions for dbt selectors."""

from collections.abc import Sequence

from sqlbuild.integrations.dbt.helpers.planning.orchestration import (
    resolve_sqlbuild_test_actions as _resolve,
)
from sqlbuild.integrations.dbt.types import DbtInteropSqlbuildTestAction


def resolve_sqlbuild_test_actions(
    *, select: Sequence[str]
) -> tuple[DbtInteropSqlbuildTestAction, ...]:
    """Map dbt test selectors to SQLBuild validation actions."""

    return _resolve(select=select)
