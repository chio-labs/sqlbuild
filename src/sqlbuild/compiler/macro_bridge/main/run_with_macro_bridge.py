"""Run one render stage through the native macro bridge, storing its calls on success."""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable
from contextvars import Token

from sqlbuild.compiler.discovery.main._require_supported_python import require_supported_python
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE, STORE_MODULE_PATHS


def run_with_macro_bridge[T](*, stage: Callable[[], T]) -> T:
    """Run `stage` once with the bridge; its errors are the Python stage's, raised as they occur."""

    python_version: tuple[int, int] = require_supported_python()
    bridge: MacroBridge = MacroBridge(
        python_version=python_version, unicode_version=unicodedata.unidata_version
    )
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
