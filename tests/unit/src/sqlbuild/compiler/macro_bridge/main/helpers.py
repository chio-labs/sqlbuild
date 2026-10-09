"""Render stages that record whether the macro bridge was active."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge


def rendered() -> str:
    """Render successfully."""

    return "rendered"


def failed() -> str:
    """Fail to render."""

    raise CompileInputError("render failed")


def failed_after_scan() -> str:
    """Fail to render after the active bridge scanned a macro call."""

    _scan_with_active_bridge()
    raise CompileInputError("render failed")


def mismatched_after_scan() -> str:
    """Report a native scan mismatch after the active bridge scanned a macro call."""

    _scan_with_active_bridge()
    raise NativeStageMismatchError("native scan ended early")


def recording_failure(*, stage: Callable[[], str], errors: list[Exception]) -> Callable[[], str]:
    """Return `stage`, recording each error it raises before it propagates."""

    def recorded() -> str:
        try:
            return stage()
        except Exception as error:
            errors.append(error)
            raise

    return recorded


def _scan_with_active_bridge() -> None:
    bridge: MacroBridge = cast(MacroBridge, active_macro_bridge())
    _ = bridge.scan("SELECT @cents('amount') AS amount")


def recording_stage(
    *, runs: list[bool], stages: dict[bool, Callable[[], str]]
) -> Callable[[], str]:
    """Return a stage recording whether each run had the bridge, then running its variant."""

    def stage() -> str:
        bridged: bool = active_macro_bridge() is not None
        runs.append(bridged)
        return stages[bridged]()

    return stage
