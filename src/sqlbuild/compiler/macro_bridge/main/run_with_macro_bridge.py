"""Run one render stage through the native macro bridge, re-running Python on any failure."""

from __future__ import annotations

import logging
import sys
import unicodedata
from collections.abc import Callable
from contextvars import Token

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import NativeRenderMismatchError
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE


def run_with_macro_bridge[T](*, stage: Callable[[], T]) -> T:
    """Run `stage` with the bridge, storing calls on success; a failure re-runs Python."""

    python_version: tuple[int, int] = (sys.version_info[0], sys.version_info[1])
    if not _native.native_text_supported(python_version, unicodedata.unidata_version):
        return stage()
    bridge: MacroBridge = MacroBridge(
        python_version=python_version, unicode_version=unicodedata.unidata_version
    )
    token: Token[object | None] = ACTIVE_MACRO_BRIDGE.set(bridge)
    native_error: Exception | None = None
    try:
        result: T = stage()
    except Exception as error:
        native_error = error
    else:
        bridge.save_store()
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
    finally:
        ACTIVE_MACRO_BRIDGE.reset(token)
    _ = stage()
    raise NativeRenderMismatchError(
        "The native macro bridge failed where the Python render succeeded; "
        "run with SQLBUILD_COMPILER_ENGINE=python"
    ) from native_error
