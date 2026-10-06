"""Public compiler engine resolution entry point."""

from sqlbuild.compiler.frontier._helpers.engine import active_compiler_engine
from sqlbuild.compiler.frontier.types import CompilerEngine


def resolve_compiler_engine() -> CompilerEngine:
    """Return the active compiler engine, raising CompilerEngineError for an unknown value."""

    return active_compiler_engine()
