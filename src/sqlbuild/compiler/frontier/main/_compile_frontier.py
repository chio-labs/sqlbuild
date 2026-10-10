"""The single seam between the compiler stages and the native frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier._helpers.native_frontier import native_frontier
from sqlbuild.compiler.frontier._helpers.stage_capture import write_stage_capture
from sqlbuild.compiler.frontier.types import CompilerStage


def compile_frontier[T](
    *,
    until: CompilerStage,
    python_stage: Callable[[], T],
    native_stage: Callable[[], T] | None = None,
) -> T:
    """Produce the frontier object for `until`, capturing it on request."""

    result: T = native_frontier(until=until, python_stage=python_stage, native_stage=native_stage)
    write_stage_capture(stage=until, value=result)
    return result
