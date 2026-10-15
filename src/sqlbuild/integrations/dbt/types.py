"""dbt integration type aliases."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DbtInvoker(Protocol):
    """Callable dbt process invocation contract."""

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None) -> object: ...
