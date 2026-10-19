"""Ask whether this compile is the process's first, so only that one uses the macro call store."""

from __future__ import annotations

from sqlbuild._native import claim_first_compile as claim_native_first_compile


def claim_first_compile() -> bool:
    """Record that a compile started; True only for the first compile invocation of this process."""

    return claim_native_first_compile()
