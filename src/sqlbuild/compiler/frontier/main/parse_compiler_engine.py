"""Public compiler engine value parsing entry point."""

from sqlbuild.compiler.frontier._helpers.engine import parse_compiler_engine as _parse
from sqlbuild.compiler.frontier.types import CompilerEngine


def parse_compiler_engine(*, raw_value: str, source: str) -> CompilerEngine:
    """Return the engine `raw_value` names, raising CompilerEngineError naming `source`."""

    return _parse(raw_value=raw_value, source=source)
