"""Enumerations shared by graph facts."""

from __future__ import annotations

from enum import StrEnum


class HookReadType(StrEnum):
    """Kind of model hook that declares or writes a read."""

    PYTHON = "Python"
    SQL = "SQL"
    INLINE_SQL = "inline SQL"
