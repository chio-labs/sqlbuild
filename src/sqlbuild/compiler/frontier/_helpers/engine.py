"""Engine parsing and environment lookup shared by the frontier entry points."""

import os

from sqlbuild.compiler.frontier.constants import (
    COMPILER_ENGINE_ENV_VAR,
    COMPILER_ENGINE_VALUES,
    DEFAULT_COMPILER_ENGINE,
    REMOVED_PYTHON_ENGINE,
)
from sqlbuild.compiler.frontier.exceptions import CompilerEngineError
from sqlbuild.compiler.frontier.types import CompilerEngine


def active_compiler_engine() -> CompilerEngine:
    """Return the engine selected by SQLBUILD_COMPILER_ENGINE, defaulting to native."""

    raw_value: str | None = os.environ.get(COMPILER_ENGINE_ENV_VAR)
    if not raw_value:
        return DEFAULT_COMPILER_ENGINE
    return parse_compiler_engine(raw_value=raw_value, source=COMPILER_ENGINE_ENV_VAR)


def parse_compiler_engine(*, raw_value: str, source: str) -> CompilerEngine:
    """Return the engine `raw_value` names, explaining the removed Python engine."""

    if raw_value == REMOVED_PYTHON_ENGINE:
        raise CompilerEngineError(
            f"{source} {REMOVED_PYTHON_ENGINE!r} is no longer supported: SQLBuild removed its "
            "Python compiler, and the native compiler is the default. Unset "
            f"{COMPILER_ENGINE_ENV_VAR} and drop --compiler-engine to use it; to run the "
            "Python compiler for comparison, pin an earlier SQLBuild release."
        )
    try:
        return CompilerEngine(raw_value)
    except ValueError as error:
        raise CompilerEngineError(
            f"{source} must be one of {', '.join(COMPILER_ENGINE_VALUES)} (got {raw_value!r})"
        ) from error
