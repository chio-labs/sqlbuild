"""Pause cyclic garbage collection around phases that build many long-lived objects."""

from __future__ import annotations

import gc
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def paused_cyclic_collection() -> Iterator[None]:
    """Skip full-heap cycle scans, then restore the prior state so only the outer pause resumes."""

    was_enabled: bool = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
