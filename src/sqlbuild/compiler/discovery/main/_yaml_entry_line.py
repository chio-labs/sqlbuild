"""Locate one named entry in an authored YAML declaration file."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

import sqlbuild._native as _native


def yaml_entry_line(*, contents: str, name: str) -> int | None:
    """Return the 1-based line of the outermost `- name: <name>` entry, if present."""

    return _entry_lines(contents).get(name)


@lru_cache(maxsize=16)
def _entry_lines(contents: str) -> Mapping[str, int]:
    return dict(_native.yaml_entry_line_index(contents))
