"""Select the compiler engine for one CLI invocation."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine


@contextmanager
def compiler_engine_override(engine: CompilerEngine | None) -> Iterator[None]:
    """Select an engine for one invocation so worker threads and subprocesses see it too."""

    if engine is None:
        yield
        return
    previous: str | None = os.environ.get(COMPILER_ENGINE_ENV_VAR)
    os.environ[COMPILER_ENGINE_ENV_VAR] = engine.value
    try:
        yield
    finally:
        if previous is None:
            _ = os.environ.pop(COMPILER_ENGINE_ENV_VAR, None)
        else:
            os.environ[COMPILER_ENGINE_ENV_VAR] = previous
