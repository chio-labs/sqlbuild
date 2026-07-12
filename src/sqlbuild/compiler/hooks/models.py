"""Public compiled lifecycle hook models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlHookEntry:
    """A model lifecycle hook that executes SQL."""

    statement: str


@dataclass(frozen=True)
class PythonHookEntry:
    """A model lifecycle hook that invokes a discovered Python hook."""

    name: str
    kwargs: dict[str, object]
