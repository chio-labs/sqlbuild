"""Test case types for layered render storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderLayerTestCase:
    """Renders changed after a stored compile, and whether they fit in an overlay."""

    description: str
    changed_models: tuple[str, ...]
    removed_models: tuple[str, ...]
    expected_overlay: bool
    expected_overlay_models: frozenset[str]


@dataclass(frozen=True)
class RenderEditChainTestCase:
    """Successive one-model edits, each stored on top of the previous compile."""

    description: str
    edits: tuple[str, ...]
    expected_overlay_models: frozenset[str]


@dataclass(frozen=True)
class StoredRenderReadTestCase:
    """A stored render file, possibly damaged, and whether reading it yields renders."""

    description: str
    prepare: Callable[[Path], tuple[Path, frozenset[str]]]
    expected_readable: bool
