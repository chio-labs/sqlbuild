"""dbt integration type aliases."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

type DbtInvoker = Callable[[tuple[str, ...], Path | None], object]


class DbtCombinedGraphOwner(StrEnum):
    """Owner namespace for a combined dbt/SQLBuild graph node."""

    DBT = "dbt"
    SQLBUILD = "sqb"


class DbtCombinedGraphResourceType(StrEnum):
    """Resource type namespace for a combined dbt/SQLBuild graph node."""

    MODEL = "model"


class DbtInteropCommand(StrEnum):
    """dbt interop commands with SQLBuild participation."""

    PLAN = "plan"
    RUN = "run"
    BUILD = "build"
    TEST = "test"
    CLONE = "clone"


class DbtInteropSkipReason(StrEnum):
    """Reason one side of a dbt interop plan has no work."""

    NO_DBT_WORK = "no_dbt_work"
    NO_SQLBUILD_WORK = "no_sqlbuild_work"
