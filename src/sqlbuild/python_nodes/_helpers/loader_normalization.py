"""Write-option normalization for Python loaders."""

from collections.abc import Sequence

from sqlbuild.spec.contracts.types import SourceWriteStrategy


def normalize_unique_key(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def normalize_write_strategy(value: str | None) -> SourceWriteStrategy | None:
    if value is None:
        return None
    return SourceWriteStrategy(value)
