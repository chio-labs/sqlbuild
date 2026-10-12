"""Run one render stage through the native macro bridge, storing its calls on success."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import Token

from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE, STORE_MODULE_PATHS


def run_with_macro_bridge[T](*, stage: Callable[[], T]) -> T:
    """Run `stage` once with the bridge; its errors are the Python stage's, raised as they occur."""

    bridge: MacroBridge = MacroBridge()
    token: Token[object | None] = ACTIVE_MACRO_BRIDGE.set(bridge)
    try:
        result: T = stage()
    finally:
        ACTIVE_MACRO_BRIDGE.reset(token)
    bridge.save_store()
    STORE_MODULE_PATHS.update(bridge.store_module_paths())
    hits, misses, recorded = bridge.stats()
    store_hits, store_records = bridge.store_stats()
    logging.getLogger(__name__).debug(
        "Native macro bridge: %d memo hits, %d store hits, %d misses, %d recorded calls, "
        "%d stored calls",
        hits,
        store_hits,
        misses,
        recorded,
        store_records,
    )
    return result
