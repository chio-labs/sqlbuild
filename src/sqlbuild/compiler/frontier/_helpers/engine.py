"""Engine parsing and environment lookup shared by the frontier entry points."""

import os

from sqlbuild.compiler.frontier.constants import (
    COMPILER_ENGINE_ENV_VAR,
    COMPILER_ENGINE_VALUES,
    DEFAULT_COMPILER_ENGINE,
)
from sqlbuild.compiler.frontier.exceptions import CompilerEngineError
from sqlbuild.compiler.frontier.types import CompilerEngine


def active_compiler_engine() -> CompilerEngine:
    """Return the engine selected by SQLBUILD_COMPILER_ENGINE, defaulting to native."""

    raw_value: str | None = os.environ.get(COMPILER_ENGINE_ENV_VAR)
    if not raw_value:
        return DEFAULT_COMPILER_ENGINE
    try:
        return CompilerEngine(raw_value)
    except ValueError as error:
        raise CompilerEngineError(
            f"{COMPILER_ENGINE_ENV_VAR} must be one of {', '.join(COMPILER_ENGINE_VALUES)} "
            f"(got {raw_value!r})"
        ) from error
