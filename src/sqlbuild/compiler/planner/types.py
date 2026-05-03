"""Planner domain types."""

from __future__ import annotations

from enum import StrEnum


class SelectorKind(StrEnum):
    NAME = "name"
    SEED = "seed"
    SOURCE = "source"
    TAG = "tag"
    PATH = "path"
