"""Built-in adapter-class entrypoint."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.discovery._helpers.builtins import adapter_class


def builtin_adapter_class(adapter_name: str) -> type[BaseAdapter] | None:
    """Load one built-in adapter class on demand."""

    return adapter_class(adapter_name)
