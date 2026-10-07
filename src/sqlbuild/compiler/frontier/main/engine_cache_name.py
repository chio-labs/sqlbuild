"""Engine namespacing for on-disk compiler stores."""

from sqlbuild.compiler.frontier._helpers.engine import active_compiler_engine
from sqlbuild.compiler.frontier.constants import ENGINE_CACHE_NAMESPACE_SUFFIXES


def engine_cache_name(base: str) -> str:
    """Name an on-disk store so engines never read each other's entries."""

    return f"{base}{ENGINE_CACHE_NAMESPACE_SUFFIXES[active_compiler_engine()]}"
