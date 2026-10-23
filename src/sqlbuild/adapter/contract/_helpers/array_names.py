"""Read object names from a warehouse array value."""

from __future__ import annotations

import json
from collections.abc import Iterable


def array_names(value: object) -> tuple[str, ...]:
    """Names from a warehouse array value: a list, an array object, or JSON text."""

    if value is None:
        return ()
    if isinstance(value, str):
        return array_names(json.loads(value)) if value.lstrip().startswith("[") else (value,)
    if not isinstance(value, Iterable):
        return (str(value),)
    return tuple(str(name) for name in value if name is not None)
