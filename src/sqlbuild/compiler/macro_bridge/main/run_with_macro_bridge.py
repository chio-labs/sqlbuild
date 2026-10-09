"""Run one render stage through the native macro bridge, storing its calls on success."""

from __future__ import annotations

import logging
import sys
import unicodedata
from collections.abc import Callable
from contextvars import Token

import sqlbuild._native as _native
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE, STORE_MODULE_PATHS


def run_with_macro_bridge[T](*, stage: Callable[[], T]) -> T:
    """Run `stage` once with the bridge; its errors are the Python stage's, raised as they occur."""

    python_version: tuple[int, int] = (sys.version_info[0], sys.version_info[1])
    if not _native.native_text_supported(python_version, unicodedata.unidata_version):
        report_native_fallback(site=NativeFallbackSite.MACRO_BRIDGE_UNAVAILABLE)
        return stage()
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
