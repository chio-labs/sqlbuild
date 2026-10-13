"""Module files that macro call results reused from the store in this process depend on."""

from __future__ import annotations

from sqlbuild.compiler.macro_bridge.constants import STORE_MODULE_PATHS


def macro_store_module_paths() -> frozenset[str]:
    """Return the module files behind stored macro call results, even ones never imported."""

    return frozenset(STORE_MODULE_PATHS)
