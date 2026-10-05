"""Stored renders of a previous compile and the render reuse of one full compile."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.models import RenderReuseState


@dataclass(frozen=True)
class StoredRenderLayer:
    """One decoded render file: its index and its payloads by key."""

    model_paths: tuple[str, ...]
    base_file: str | None
    models: dict[str, memoryview]
    groups: dict[str, memoryview]
    size: int


@dataclass(frozen=True)
class StoredRenderLayers:
    """How a stored compile's renders are split between a base file and one overlay."""

    base_file: str
    base_bytes: int
    overlay_models: frozenset[str]
    overlay_groups: frozenset[str]


@dataclass(frozen=True)
class StoredRenderState:
    """Renders a stored compile recorded, merged across layers, with their layout."""

    state: RenderReuseState
    layers: StoredRenderLayers


@dataclass(frozen=True)
class CompileRenderReuse:
    """One full compile's render reuse session with the stored renders it started from."""

    session: CompileRenderReuseSession
    stored: StoredRenderState | None
