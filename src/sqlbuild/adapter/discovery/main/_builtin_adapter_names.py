"""Built-in adapter-name entrypoint."""

from sqlbuild.adapter.discovery._helpers.builtins import adapter_names


def builtin_adapter_names() -> frozenset[str]:
    """Return every reserved built-in adapter name without loading implementations."""

    return adapter_names()
