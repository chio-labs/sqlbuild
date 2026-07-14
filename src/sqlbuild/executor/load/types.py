"""Load executor callback types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.spec.contracts.models import SourceEntry


class LoadProgressCallback(Protocol):
    def __call__(self, source: SourceEntry, *, message: str) -> None: ...
