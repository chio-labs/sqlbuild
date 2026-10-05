"""Checksummed, layered storage for the renders of the compile one stored entry describes."""

from __future__ import annotations

import json
import zlib
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from sqlbuild.cli.compile_render_reuse.constants import (
    RENDER_COMPRESSION_LEVEL,
    RENDER_INDEX_FIELD_COUNT,
    RENDER_OVERLAY_MAX_SHARE,
    RENDER_STATE_MAGIC,
)
from sqlbuild.cli.compile_render_reuse.models import (
    StoredRenderLayer,
    StoredRenderLayers,
    StoredRenderState,
)
from sqlbuild.cli.compile_reuse.constants import (
    REUSE_ENTRY_BYTE_ORDER,
    REUSE_ENTRY_CHECKSUM_BYTES,
    REUSE_ENTRY_LENGTH_BYTES,
    REUSE_MAX_ENTRY_BYTES,
    REUSE_RENDER_STATE_SUFFIX,
)
from sqlbuild.cli.compile_reuse.exceptions import CompileReuseEntryError
from sqlbuild.cli.compile_reuse.main._framed_section import framed_stored_section
from sqlbuild.cli.compile_reuse.main._read_framed_section import read_stored_section
from sqlbuild.cli.compile_reuse.models import RenderStateLayer
from sqlbuild.compiler.compile.models import RenderReuseState


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
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError, zlib.error):
        return None


def render_state_layer(
    *, state: RenderReuseState, stored: StoredRenderLayers | None
) -> RenderStateLayer | None:
    """Return an overlay on the stored base, a new base, or None when released bytes are needed."""

    if (
        stored is not None
        and state.model_paths == stored.model_paths
        and stored.model_keys <= state.model_payloads.keys()
        and stored.group_keys <= state.group_payloads.keys()
    ):
        models: list[tuple[str, memoryview]] = _held(
            (path, state.model_payloads.get(path)) for path in state.model_paths
        )
        groups: list[tuple[str, memoryview]] = _held(sorted(state.group_payloads.items()))
        if (
            sum(len(item) for _, item in (*models, *groups))
            <= stored.base_bytes * RENDER_OVERLAY_MAX_SHARE
        ):
            return _layer(
                model_paths=state.model_paths,
                base_file=stored.base_file,
                models=models,
                groups=groups,
            )
    if None in state.model_payloads.values() or None in state.group_payloads.values():
        return None
    return _layer(
        model_paths=state.model_paths,
        base_file=None,
        models=_held((path, state.model_payloads.get(path)) for path in state.model_paths),
        groups=_held(sorted(state.group_payloads.items())),
    )


def _held(items: Iterable[tuple[str, memoryview | None]]) -> list[tuple[str, memoryview]]:
    return [(key, payload) for key, payload in items if payload is not None]


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
    compressor: zlib._Compress = zlib.compressobj(RENDER_COMPRESSION_LEVEL)
    compressed: list[bytes] = [compressor.compress(item) for _, item in (*models, *groups)]
    compressed.append(compressor.flush())
    return RenderStateLayer(
        chunks=(
            RENDER_STATE_MAGIC,
            framed_stored_section(data=index),
            _section_header(payloads=compressed),
            *compressed,
        ),
        base_file=base_file,
    )


def _section_header(*, payloads: Iterable[bytes]) -> bytes:
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
        if handle.read(len(RENDER_STATE_MAGIC)) != RENDER_STATE_MAGIC:
            return None
        index: object = json.loads(read_stored_section(handle=handle))
        if not isinstance(index, dict):
            return None
        fields: dict[str, object] = cast(dict[str, object], index)
        model_paths: tuple[str, ...] = tuple(_string(item) for item in _list(fields["model_paths"]))
        if not changed_paths.issubset(model_paths):
            return None
        compressed: bytes = read_stored_section(handle=handle)
        if handle.read(1) or len(compressed) > REUSE_MAX_ENTRY_BYTES:
            return None
    base: object = fields["base"]
    model_rows: list[tuple[str, int]] = _rows(fields["models"])
    group_rows: list[tuple[str, int]] = _rows(fields["groups"])
    size: int = sum(length for _, length in (*model_rows, *group_rows))
    if size > REUSE_MAX_ENTRY_BYTES:
        return None
    decompressor: zlib._Decompress = zlib.decompressobj()
    payload: bytes = decompressor.decompress(compressed, size + 1)
    del compressed
    if len(payload) != size or not decompressor.eof or decompressor.unconsumed_tail:
        return None
    view: memoryview = memoryview(payload)
    offset: int = 0
    models: dict[str, memoryview] = {}
    for name, length in model_rows:
        models[name] = view[offset : offset + length]
        offset += length
    groups: dict[str, memoryview] = {}
    for name, length in group_rows:
        groups[name] = view[offset : offset + length]
        offset += length
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
    state: RenderReuseState = RenderReuseState(
        model_paths=newest.model_paths,
        model_payloads=dict(base.models) if overlay is None else {**base.models, **overlay.models},
        group_payloads=dict(base.groups) if overlay is None else {**base.groups, **overlay.groups},
    )
    return StoredRenderState(
        state=state,
        layers=StoredRenderLayers(
            model_paths=newest.model_paths,
            model_keys=frozenset(state.model_payloads),
            group_keys=frozenset(state.group_payloads),
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
        if len(items) != RENDER_INDEX_FIELD_COUNT:
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
