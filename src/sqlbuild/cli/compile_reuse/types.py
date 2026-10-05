"""Compile reuse outcome and file stamp types."""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class CompileReuseOutcome(StrEnum):
    """How one compile invocation used the stored previous compile."""

    HIT = "hit"
    MISS = "miss"
    BYPASS = "bypass"


class FileStamp(NamedTuple):
    """Filesystem identity of one project path, as seen by a stat walk."""

    kind: str
    size: int
    mtime_ns: int
    ctime_ns: int
    inode: int
    link: str | None
