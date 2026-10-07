"""The macro bridge of the running native render stage."""

from __future__ import annotations

from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import ACTIVE_MACRO_BRIDGE


def active_macro_bridge() -> MacroBridge | None:
    """Return the macro bridge of the running native render stage, if any."""

    bridge: object | None = ACTIVE_MACRO_BRIDGE.get()
    return bridge if isinstance(bridge, MacroBridge) else None
