"""The native side of the compiler frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier.types import CompilerStage
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
    if until is CompilerStage.COMPILE_PROJECT_INPUTS:
        return run_with_macro_bridge(stage=python_stage)
    return python_stage()
