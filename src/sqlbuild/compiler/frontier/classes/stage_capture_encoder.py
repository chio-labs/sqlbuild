"""Convert frontier objects into canonical JSON-compatible values."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import functools
import hashlib
import json
import math
import re
import types
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import PurePath
from typing import Any

from sqlbuild.compiler.frontier.constants import (
    STAGE_CAPTURE_DECODED_SEQUENCES,
    STAGE_CAPTURE_ENGINE_NAMESPACE_PATTERN,
    STAGE_CAPTURE_INVOCATION_ID_MASK,
    STAGE_CAPTURE_INVOCATION_ID_PATTERN,
    STAGE_CAPTURE_OMITTED_ATTRIBUTES,
    STAGE_CAPTURE_REFACTOR_STAGING_MASK,
    STAGE_CAPTURE_REFACTOR_STAGING_PATTERN,
    STAGE_CAPTURE_RESERVED_KEYS,
    STAGE_CAPTURE_SHARED_MARKER,
    STAGE_CAPTURE_SHARED_MIN_BYTES,
    STAGE_CAPTURE_SKIPPED_SLOTS,
    STAGE_CAPTURE_UNORDERED_ATTRIBUTES,
)

_CALLABLE_TYPES: tuple[type, ...] = (
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
    types.BuiltinMethodType,
    type,
)


class StageCaptureEncoder:
    """Encode an object graph deterministically, sharing large subtrees by content digest."""

    def __init__(
        self,
        *,
        on_shared: Callable[..., None] | None = None,
        share_min_bytes: int = STAGE_CAPTURE_SHARED_MIN_BYTES,
    ) -> None:
        self._active: set[int] = set()
        self._cycles: int = 0
        self._encoded: dict[int, tuple[object, object]] = {}
        self._on_shared: Callable[..., None] | None = on_shared
        self._share_min_bytes: int = share_min_bytes
        self._digests: set[str] = set()

    def encode(self, value: object) -> object:
        """Return a JSON-compatible value that keeps insertion order and sorts only sets."""

        if isinstance(value, enum.Enum):
            return {"__enum__": f"{qualified_name(type(value))}.{value.name}"}
        if isinstance(value, str):
            return value if len(value) < self._share_min_bytes else self._share(value)
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else {"__float__": repr(value)}
        scalar: object | None = _encode_scalar(value)
        if scalar is not None:
            return scalar
        identity: int = id(value)
        if identity in self._active:
            self._cycles += 1
            return {"__cycle__": qualified_name(type(value))}
        known: tuple[object, object] | None = self._encoded.get(identity)
        if known is not None:
            return known[1]
        cycles: int = self._cycles
        self._active.add(identity)
        try:
            encoded: object = self._share(self._encode_container(value))
        finally:
            self._active.discard(identity)
        if self._cycles == cycles:
            self._encoded[identity] = (value, encoded)
        return encoded

    def _share(self, encoded: object) -> object:
        if self._on_shared is None or not isinstance(encoded, (dict, list, str)):
            return encoded
        text: str = json.dumps(encoded, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(text) < self._share_min_bytes:
            return encoded
        digest: str = hashlib.sha256(mask_capture_noise(text).encode("utf-8")).hexdigest()
        if digest not in self._digests:
            self._digests.add(digest)
            self._on_shared(digest=digest, text=text)
        return {STAGE_CAPTURE_SHARED_MARKER: digest}

    def _encode_container(self, value: object) -> object:
        type_name: str = qualified_name(type(value))
        if type_name in STAGE_CAPTURE_DECODED_SEQUENCES and isinstance(value, Sequence):
            return [self.encode(item) for item in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            omitted_fields: frozenset[str] = STAGE_CAPTURE_OMITTED_ATTRIBUTES.get(
                type_name, frozenset()
            )
            return {
                "__type__": type_name,
                **{
                    field.name: self.encode(getattr(value, field.name, None))
                    for field in dataclasses.fields(value)
                    if field.name not in omitted_fields
                },
            }
        if isinstance(value, Mapping):
            return self._encode_mapping(value)
        if isinstance(value, AbstractSet):
            return {"__set__": sorted((self.encode(item) for item in value), key=_sort_key)}
        if isinstance(value, (list, tuple)):
            return [self.encode(item) for item in value]
        if isinstance(value, functools.partial):
            return {
                "__partial__": self.encode(value.func),
                "args": self.encode(value.args),
                "keywords": self.encode(value.keywords),
            }
        attributes: dict[str, object] | None = _instance_attributes(value)
        if attributes is None:
            return {"__opaque__": type_name}
        unordered: frozenset[str] = STAGE_CAPTURE_UNORDERED_ATTRIBUTES.get(type_name, frozenset())
        omitted: frozenset[str] = STAGE_CAPTURE_OMITTED_ATTRIBUTES.get(type_name, frozenset())
        return {
            "__type__": type_name,
            **{
                name: self._encode_attribute(value=item, unordered=name in unordered)
                for name, item in attributes.items()
                if name not in omitted
            },
        }

    def _encode_attribute(self, *, value: object, unordered: bool) -> object:
        if not unordered or not isinstance(value, Mapping):
            return self.encode(value)
        return {"__unordered_mapping__": sorted(self._mapping_pairs(value), key=_sort_key)}

    def _encode_mapping(self, value: Mapping[Any, object]) -> object:
        if all(isinstance(key, str) for key in value) and STAGE_CAPTURE_RESERVED_KEYS.isdisjoint(
            value
        ):
            return {str(key): self.encode(item) for key, item in value.items()}
        return {"__mapping__": self._mapping_pairs(value)}

    def _mapping_pairs(self, value: Mapping[Any, object]) -> list[list[object]]:
        return [[self.encode(key), self.encode(item)] for key, item in value.items()]


def qualified_name(value: object) -> str:
    """Return `module:qualname` for a callable or class."""

    module: object = getattr(value, "__module__", None)
    name: object = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if name is None:
        return qualified_name(type(value))
    return f"{module}:{name}" if isinstance(module, str) else str(name)


def _encode_scalar(value: object) -> object | None:
    if isinstance(value, PurePath):
        return {"__path__": value.as_posix()}
    if isinstance(value, decimal.Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, (datetime.date, datetime.time)):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        data: bytes = bytes(value)
        return {"__bytes__": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if isinstance(value, re.Pattern):
        return {"__pattern__": str(value.pattern)}
    if isinstance(value, types.ModuleType):
        return {"__module__": value.__name__}
    if isinstance(value, _CALLABLE_TYPES):
        return {"__callable__": qualified_name(value)}
    return None


def mask_capture_noise(text: str) -> str:
    """Mask invocation ids, native store suffixes and refactor staging folders of a compile."""

    masked: str = STAGE_CAPTURE_ENGINE_NAMESPACE_PATTERN.sub(
        "",
        STAGE_CAPTURE_INVOCATION_ID_PATTERN.sub(STAGE_CAPTURE_INVOCATION_ID_MASK, text),
    )
    return STAGE_CAPTURE_REFACTOR_STAGING_PATTERN.sub(STAGE_CAPTURE_REFACTOR_STAGING_MASK, masked)


def _sort_key(item: object) -> str:
    return mask_capture_noise(json.dumps(item, sort_keys=True, ensure_ascii=False))


def _instance_attributes(value: object) -> dict[str, object] | None:
    instance_dict: object = getattr(value, "__dict__", None)
    attributes: dict[str, object] = (
        {str(name): item for name, item in instance_dict.items()}
        if isinstance(instance_dict, dict)
        else {}
    )
    for cls in type(value).__mro__:
        slots: object = cls.__dict__.get("__slots__", ())
        for name in (slots,) if isinstance(slots, str) else slots:
            if (
                isinstance(name, str)
                and name not in STAGE_CAPTURE_SKIPPED_SLOTS
                and hasattr(value, name)
            ):
                attributes[name] = getattr(value, name)
    if not attributes and not isinstance(instance_dict, dict):
        return None
    return attributes
