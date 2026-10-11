"""Module sources a stored macro call result depends on."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSources:
    """Files backing loaded modules, and whether every module's backing could be identified."""

    paths: tuple[str, ...]
    complete: bool
