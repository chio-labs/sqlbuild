"""Constants for path-default glob matching."""

from __future__ import annotations

SINGLE_SEGMENT_GLOB: str = "*"
RECURSIVE_SEGMENT_GLOB: str = "**"
GLOB_SEGMENTS: frozenset[str] = frozenset({SINGLE_SEGMENT_GLOB, RECURSIVE_SEGMENT_GLOB})
UNSUPPORTED_GLOB_MARKERS: tuple[str, ...] = (SINGLE_SEGMENT_GLOB, "?", "[")
