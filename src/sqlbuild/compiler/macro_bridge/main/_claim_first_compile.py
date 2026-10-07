"""Count the compiles this process has started, so only its first one uses the macro call store."""

from __future__ import annotations

from sqlbuild.compiler.macro_bridge.constants import COMPILES_STARTED


def claim_first_compile() -> bool:
    """Record that a compile started; True only for the first compile of this process."""

    return next(COMPILES_STARTED) == 0
