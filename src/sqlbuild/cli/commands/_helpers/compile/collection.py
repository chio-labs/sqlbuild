"""Pause cyclic garbage collection while one compile builds its long-lived project state."""

from __future__ import annotations

import gc
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def paused_cyclic_collection() -> Iterator[None]:
    """Skip full-heap cycle scans of long-lived compile state, then restore the prior state."""

    was_enabled: bool = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
