"""Digest whole-project fact values whose resources share large compiler objects."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable

import orjson

from sqlbuild.rule_engine.constants import SHARED_FACT_DATACLASS_TAG


class SharedFactEncoder:
    """Encode each compiler dataclass once and refer to it by digest wherever it repeats."""

    def __init__(self, *, options: int, encode_default: Callable[[object], object]) -> None:
        self._options: int = options | orjson.OPT_PASSTHROUGH_DATACLASS
        self._encode_default: Callable[[object], object] = encode_default
        self._fields: dict[type, tuple[str, ...]] = {}
        self._digests: dict[int, tuple[object, str]] = {}

    def encode(self, value: object) -> bytes:
        return orjson.dumps(value, default=self._default, option=self._options)

    def _default(self, value: object) -> object:
        kind: type = type(value)
        names: tuple[str, ...] | None = self._fields.get(kind)
        if names is None:
            if not dataclasses.is_dataclass(kind):
                return self._encode_default(value)
            names = tuple(field.name for field in dataclasses.fields(kind))
            self._fields[kind] = names
        cached: tuple[object, str] | None = self._digests.get(id(value))
        if cached is None:
            encoded: bytes = self.encode(
                [f"{kind.__module__}.{kind.__qualname__}", [getattr(value, name) for name in names]]
            )
            cached = (value, hashlib.sha256(encoded).hexdigest())
            self._digests[id(value)] = cached
        return [SHARED_FACT_DATACLASS_TAG, cached[1]]
