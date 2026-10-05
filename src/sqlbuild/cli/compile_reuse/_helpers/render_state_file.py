"""Checksummed, layered storage for the renders of the compile one stored entry describes."""

from __future__ import annotations

import json
import zlib
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from sqlbuild.cli.compile_reuse._helpers.entry_file import framed_section, read_framed_section
from sqlbuild.cli.compile_reuse.constants import (
    REUSE_ENTRY_BYTE_ORDER,
    REUSE_ENTRY_CHECKSUM_BYTES,
    REUSE_ENTRY_LENGTH_BYTES,
    REUSE_MAX_ENTRY_BYTES,
    REUSE_RENDER_OVERLAY_MAX_SHARE,
    REUSE_RENDER_STATE_MAGIC,
    REUSE_RENDER_STATE_SUFFIX,
)
from sqlbuild.cli.compile_reuse.exceptions import CompileReuseEntryError
from sqlbuild.cli.compile_reuse.models import (
    RenderStateLayer,
    StoredRenderLayer,
    StoredRenderLayers,
    StoredRenderState,
)
from sqlbuild.compiler.compile.models import RenderReuseState

_INDEX_FIELD_COUNT: int = 2


def read_render_state(*, path: Path, changed_paths: frozenset[str]) -> StoredRenderState | None:
    """Read verified renders when every changed path is a stored model; any fault means none."""

    try:
        newest: StoredRenderLayer | None = _read_layer(path=path, changed_paths=changed_paths)
        if newest is None:
            return None
        if newest.base_file is None:
            return _stored_state(base_file=path.name, base=newest, overlay=None)
        base: StoredRenderLayer | None = _read_layer(
            path=path.parent / _layer_name(newest.base_file), changed_paths=frozenset()
        )
        if base is None or base.base_file is not None:
            return None
        return _stored_state(base_file=newest.base_file, base=base, overlay=newest)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        return None


def render_state_layer(
    *, state: RenderReuseState, stored: StoredRenderState | None
) -> RenderStateLayer:
    """Extend the stored base with a small overlay of changed renders, or write a new base."""

    if stored is not None and state.model_paths == stored.state.model_paths:
        overlay_models: frozenset[str] | None = _overlay_keys(
            current=state.model_payloads,
            previous=stored.state.model_payloads,
            overlay=stored.layers.overlay_models,
        )
        overlay_groups: frozenset[str] | None = _overlay_keys(
            current=state.group_payloads,
            previous=stored.state.group_payloads,
            overlay=stored.layers.overlay_groups,
        )
        if overlay_models is not None and overlay_groups is not None:
            models: list[tuple[str, memoryview]] = [
                (path, state.model_payloads[path])
                for path in state.model_paths
                if path in overlay_models
            ]
            groups: list[tuple[str, memoryview]] = sorted(
                (name, state.group_payloads[name]) for name in overlay_groups
            )
            if (
                sum(len(item) for _, item in (*models, *groups))
                <= stored.layers.base_bytes * REUSE_RENDER_OVERLAY_MAX_SHARE
            ):
                return _layer(
                    model_paths=state.model_paths,
                    base_file=stored.layers.base_file,
                    models=models,
                    groups=groups,
                )
    return _layer(
        model_paths=state.model_paths,
        base_file=None,
        models=[
            (path, state.model_payloads[path])
            for path in state.model_paths
            if path in state.model_payloads
        ],
        groups=sorted(state.group_payloads.items()),
    )


def _overlay_keys(
    *,
    current: dict[str, memoryview],
    previous: dict[str, memoryview],
    overlay: frozenset[str],
) -> frozenset[str] | None:
    """Return keys the overlay must hold, or None when a stored render is no longer valid."""

    if not previous.keys() <= current.keys():
        return None
    return overlay | {key for key, payload in current.items() if previous.get(key) is not payload}


def _layer(
    *,
    model_paths: tuple[str, ...],
    base_file: str | None,
    models: list[tuple[str, memoryview]],
    groups: list[tuple[str, memoryview]],
) -> RenderStateLayer:
    index: bytes = json.dumps(
        {
            "model_paths": list(model_paths),
            "base": base_file,
            "models": [[path, len(payload)] for path, payload in models],
            "groups": [[name, len(payload)] for name, payload in groups],
        },
        separators=(",", ":"),
    ).encode("utf-8", "surrogateescape")
    payloads: tuple[memoryview, ...] = tuple(item for _, item in (*models, *groups))
    return RenderStateLayer(
        chunks=(
            REUSE_RENDER_STATE_MAGIC,
            framed_section(data=index),
            _section_header(payloads=payloads),
            *payloads,
        ),
        base_file=base_file,
    )


def _section_header(*, payloads: Iterable[memoryview]) -> bytes:
    length: int = 0
    checksum: int = 0
    for payload in payloads:
        length += len(payload)
        checksum = zlib.crc32(payload, checksum)
    return length.to_bytes(REUSE_ENTRY_LENGTH_BYTES, REUSE_ENTRY_BYTE_ORDER) + checksum.to_bytes(
        REUSE_ENTRY_CHECKSUM_BYTES, REUSE_ENTRY_BYTE_ORDER
    )


def _read_layer(*, path: Path, changed_paths: frozenset[str]) -> StoredRenderLayer | None:
    with open(path, "rb") as handle:
        if handle.read(len(REUSE_RENDER_STATE_MAGIC)) != REUSE_RENDER_STATE_MAGIC:
            return None
        index: object = json.loads(read_framed_section(handle=handle))
        if not isinstance(index, dict):
            return None
        fields: dict[str, object] = cast(dict[str, object], index)
        model_paths: tuple[str, ...] = tuple(_string(item) for item in _list(fields["model_paths"]))
        if not changed_paths.issubset(model_paths):
            return None
        payload: bytes = read_framed_section(handle=handle)
        if handle.read(1) or len(payload) > REUSE_MAX_ENTRY_BYTES:
            return None
    base: object = fields["base"]
    view: memoryview = memoryview(payload)
    offset: int = 0
    models: dict[str, memoryview] = {}
    for name, length in _rows(fields["models"]):
        models[name] = view[offset : offset + length]
        offset += length
    groups: dict[str, memoryview] = {}
    for name, length in _rows(fields["groups"]):
        groups[name] = view[offset : offset + length]
        offset += length
    if offset != len(view):
        return None
    return StoredRenderLayer(
        model_paths=model_paths,
        base_file=None if base is None else _string(base),
        models=models,
        groups=groups,
        size=len(payload),
    )


def _stored_state(
    *, base_file: str, base: StoredRenderLayer, overlay: StoredRenderLayer | None
) -> StoredRenderState:
    newest: StoredRenderLayer = base if overlay is None else overlay
    return StoredRenderState(
        state=RenderReuseState(
            model_paths=newest.model_paths,
            model_payloads=base.models if overlay is None else {**base.models, **overlay.models},
            group_payloads=base.groups if overlay is None else {**base.groups, **overlay.groups},
        ),
        layers=StoredRenderLayers(
            base_file=base_file,
            base_bytes=base.size,
            overlay_models=frozenset() if overlay is None else frozenset(overlay.models),
            overlay_groups=frozenset() if overlay is None else frozenset(overlay.groups),
        ),
    )


def _layer_name(name: str) -> str:
    if Path(name).name != name or not name.endswith(REUSE_RENDER_STATE_SUFFIX):
        raise CompileReuseEntryError("invalid stored render base name")
    return name


def _rows(value: object) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for row in _list(value):
        items: list[object] = _list(row)
        if len(items) != _INDEX_FIELD_COUNT:
            raise CompileReuseEntryError("invalid stored render index")
        length: object = items[1]
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            raise CompileReuseEntryError("invalid stored render length")
        rows.append((_string(items[0]), length))
    return rows


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise CompileReuseEntryError("invalid stored render list")
    return cast(list[object], value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise CompileReuseEntryError("invalid stored render string")
    return value
