"""Shared CLI command models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NestedProgressChildRow:
    """One child row rendered below a completed nested progress item."""

    label: str
    name: str
    status_text: str
    detail: str = ""
