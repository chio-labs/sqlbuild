"""Return memory the C allocator keeps after earlier compile phases freed it."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from functools import cache
from typing import Any


def release_freed_memory() -> None:
    """Hand freed glibc heap pages back to the OS; a no-op on other platforms and allocators."""

    trim: Callable[[int], int] | None = _malloc_trim()
    if trim is not None:
        _ = trim(0)


@cache
def _malloc_trim() -> Callable[[int], int] | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        trim: Any = ctypes.CDLL(None).malloc_trim
    except (OSError, AttributeError):
        return None
    trim.argtypes = (ctypes.c_size_t,)
    trim.restype = ctypes.c_int
    return trim
