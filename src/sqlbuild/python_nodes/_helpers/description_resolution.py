"""Description resolution for decorated Python-node functions."""

import inspect
from collections.abc import Callable


def resolve_description(*, function: Callable[..., object], description: str | None) -> str | None:
    return description if description is not None else inspect.getdoc(function)
