"""Render stages that record whether the macro bridge was active."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge


def rendered() -> str:
    """Render successfully."""

    return "rendered"


def failed() -> str:
    """Fail to render."""

    raise CompileInputError("render failed")


def recording_stage(
    *, runs: list[bool], stages: dict[bool, Callable[[], str]]
) -> Callable[[], str]:
    """Return a stage recording whether each run had the bridge, then running its variant."""

    def stage() -> str:
        bridged: bool = active_macro_bridge() is not None
        runs.append(bridged)
        return stages[bridged]()

    return stage
