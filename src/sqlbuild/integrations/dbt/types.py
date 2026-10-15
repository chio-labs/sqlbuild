"""dbt integration type aliases."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DbtInvoker(Protocol):
    """Callable dbt process invocation contract."""

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None) -> object: ...


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
