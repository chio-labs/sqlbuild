"""Fingerprint callable contracts."""

from __future__ import annotations

from typing import Protocol


class FingerprintWriteProgress(Protocol):
    def __call__(self, *, completed: int, total: int) -> None: ...
