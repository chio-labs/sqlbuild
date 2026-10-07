"""Macro call presence over authored model config, answered natively."""

from __future__ import annotations

import sqlbuild._native as _native


def native_config_contains_macro_call(value: object) -> bool | None:
    """Return whether any nested string holds a macro call, or None where Python must scan."""

    return _native.config_contains_macro_call(value)
