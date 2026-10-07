"""The native side of the compiler frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import CompilerStage, NativeStage
from sqlbuild.compiler.macro_bridge.main.run_with_macro_bridge import run_with_macro_bridge


def native_frontier[T](
    *,
    until: CompilerStage,
    python_stage: Callable[[], T],
    native_stage: Callable[[], T] | None,
) -> T:
    """Produce the frontier object for `until` natively; stages not yet native run in Python."""

    if native_stage is not None:
        return native_stage()
    if until is CompilerStage.COMPILE_PROJECT_INPUTS and native_stage_enabled(
        NativeStage.MACRO_CALLS
    ):
        return run_with_macro_bridge(stage=python_stage)
    return python_stage()
