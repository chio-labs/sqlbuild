"""dbt integration type aliases."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DbtInvoker(Protocol):
    """Callable dbt process invocation contract."""

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None) -> object: ...


class DbtCombinedGraphOwner(StrEnum):
    """Owner namespace for a combined dbt/SQLBuild graph node."""

    DBT = "dbt"
    SQLBUILD = "sqb"


class DbtCombinedGraphResourceType(StrEnum):
    """Resource type namespace for a combined dbt/SQLBuild graph node."""

    MODEL = "model"
    SOURCE = "source"


class DbtSupportedResourceType(StrEnum):
    """dbt resource types SQLBuild currently handles with dedicated behavior."""

    MODEL = "model"
    SEED = "seed"
    SNAPSHOT = "snapshot"
    SOURCE = "source"
    TEST = "test"
    UNIT_TEST = "unit_test"


class DbtInteropCommand(StrEnum):
    """dbt interop commands with SQLBuild participation."""

    PLAN = "plan"
    RUN = "run"
    BUILD = "build"
    DEBUG = "debug"


class DbtInteropSkipReason(StrEnum):
    """Reason one side of a dbt interop plan has no work."""

    NO_DBT_WORK = "no_dbt_work"
    NO_SQLBUILD_WORK = "no_sqlbuild_work"
