"""The native side of the compiler frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier.types import CompilerStage


def native_frontier[T](
    *,
    until: CompilerStage,
    python_stage: Callable[[], T],
    native_stage: Callable[[], T] | None,
) -> T:
    """Produce the frontier object for `until` natively; stages not yet native run in Python."""

    _ = until
    return python_stage() if native_stage is None else native_stage()
