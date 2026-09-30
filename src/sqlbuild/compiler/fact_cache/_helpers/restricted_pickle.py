"""Pickle codec restricted to SQLBuild value types for local fact cache payloads."""

from __future__ import annotations

import dataclasses
import enum
import io
import pickle
from typing import override

from sqlbuild.compiler.fact_cache.constants import (
    FACT_CACHE_ALLOWED_GLOBALS,
    FACT_CACHE_ALLOWED_PACKAGE,
    FACT_CACHE_PICKLE_PROTOCOL,
)
from sqlbuild.compiler.fact_cache.exceptions import FactCachePayloadError


class _RestrictedUnpickler(pickle.Unpickler):
    """Resolve only immutable-value classes, never functions or arbitrary callables."""

    @override
    def find_class(self, module: str, name: str) -> type:
        if (module, name) in FACT_CACHE_ALLOWED_GLOBALS:
            resolved: object = super().find_class(module, name)
            if isinstance(resolved, type):
                return resolved
        if module == FACT_CACHE_ALLOWED_PACKAGE or module.startswith(
            f"{FACT_CACHE_ALLOWED_PACKAGE}."
        ):
            resolved = super().find_class(module, name)
            if isinstance(resolved, type) and (
                dataclasses.is_dataclass(resolved)
                or issubclass(resolved, enum.Enum)
                or (issubclass(resolved, tuple) and hasattr(resolved, "_fields"))
            ):
                return resolved
        raise FactCachePayloadError(f"fact cache payload references disallowed {module}.{name}")


def dump_fact_payload(value: object) -> bytes:
    """Serialize one cache value with the fixed fact-cache protocol."""

    return pickle.dumps(value, protocol=FACT_CACHE_PICKLE_PROTOCOL)


def load_fact_payload(payload: bytes) -> object:
    """Deserialize one verified cache payload through the restricted class allowlist."""

    return _RestrictedUnpickler(io.BytesIO(payload)).load()
