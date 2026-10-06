"""Engine namespacing for on-disk compiler stores."""

from sqlbuild.compiler.frontier._helpers.engine import active_compiler_engine
from sqlbuild.compiler.frontier.constants import NATIVE_CACHE_NAMESPACE_SUFFIX
from sqlbuild.compiler.frontier.types import CompilerEngine


def engine_cache_name(base: str) -> str:
    """Name an on-disk store so engines never read each other's entries."""

    if active_compiler_engine() is CompilerEngine.PYTHON:
        return base
    return f"{base}{NATIVE_CACHE_NAMESPACE_SUFFIX}"
