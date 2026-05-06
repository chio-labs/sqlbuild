from __future__ import annotations

from collections.abc import Callable


def raise_import_error_for(expected_name: str) -> Callable[[str], object]:
    def _raise_import_error(name: str) -> object:
        if name == expected_name:
            raise ImportError(name)
        raise AssertionError(f"unexpected import {name}")

    return _raise_import_error
