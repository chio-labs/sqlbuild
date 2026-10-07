"""Macro call sites found by the native scan."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroCallSite:
    """One top-level macro call in an authored string, in Python string offsets."""

    start: int
    end: int
    name: str
    tree_names: tuple[str, ...]
    typed_reference_text: bool
