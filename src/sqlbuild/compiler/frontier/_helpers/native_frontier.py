"""The native side of the compiler frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier.types import CompilerStage


def native_frontier[T](*, until: CompilerStage, python_stage: Callable[[], T]) -> T:
    """Produce the frontier object for `until` natively; no stage is native yet."""

    _ = until
    return python_stage()
