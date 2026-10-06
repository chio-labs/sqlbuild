"""The single seam between the Python compiler stages and the native frontier."""

from collections.abc import Callable

from sqlbuild.compiler.frontier._helpers.engine import active_compiler_engine
from sqlbuild.compiler.frontier._helpers.native_frontier import native_frontier
from sqlbuild.compiler.frontier._helpers.stage_capture import write_stage_capture
from sqlbuild.compiler.frontier.types import CompilerEngine, CompilerStage


def compile_frontier[T](*, until: CompilerStage, python_stage: Callable[[], T]) -> T:
    """Produce the frontier object for `until` on the active engine, capturing it on request."""

    result: T = (
        python_stage()
        if active_compiler_engine() is CompilerEngine.PYTHON
        else native_frontier(until=until, python_stage=python_stage)
    )
    write_stage_capture(stage=until, value=result)
    return result
