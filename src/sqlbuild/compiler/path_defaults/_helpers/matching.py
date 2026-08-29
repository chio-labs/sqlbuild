"""Path-default glob matching mechanics."""

from __future__ import annotations

from functools import cache

from sqlbuild.compiler.path_defaults.constants import (
    GLOB_SEGMENTS,
    RECURSIVE_SEGMENT_GLOB,
    SINGLE_SEGMENT_GLOB,
)


def matches_prefix(*, path_parts: tuple[str, ...], path_key: str) -> bool:
    """Return whether a path-default pattern matches a prefix of a model path."""

    pattern_parts: tuple[str, ...] = tuple(path_key.split("/"))

    @cache
    def matches(*, pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return True
        pattern_part: str = pattern_parts[pattern_index]
        if pattern_part == RECURSIVE_SEGMENT_GLOB:
            return matches(pattern_index=pattern_index + 1, path_index=path_index) or (
                path_index < len(path_parts)
                and matches(pattern_index=pattern_index, path_index=path_index + 1)
            )
        if path_index == len(path_parts):
            return False
        if pattern_part == SINGLE_SEGMENT_GLOB or pattern_part == path_parts[path_index]:
            return matches(pattern_index=pattern_index + 1, path_index=path_index + 1)
        return False

    return matches(pattern_index=0, path_index=0)


def is_wildcard(*, path_key: str) -> bool:
    """Return whether a path-default key contains a supported wildcard segment."""

    return any(part in GLOB_SEGMENTS for part in path_key.split("/"))


def specificity(*, path_key: str) -> tuple[int, int, int]:
    """Return deterministic wildcard specificity based on literal path structure."""

    parts: tuple[str, ...] = tuple(path_key.split("/"))
    literal_count: int = sum(part not in GLOB_SEGMENTS for part in parts)
    single_segment_count: int = parts.count(SINGLE_SEGMENT_GLOB)
    recursive_count: int = parts.count(RECURSIVE_SEGMENT_GLOB)
    return literal_count, single_segment_count, -recursive_count
