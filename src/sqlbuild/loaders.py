"""Public decorator API for SQLBuild source loaders."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.python_nodes.main.apply_loader import apply_loader
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.models import LoaderDefinition
from sqlbuild.python_nodes.types import LoaderColumnSpec
from sqlbuild.spec.contracts.models import SourceColumnEntry
from sqlbuild.spec.contracts.types import SourceWriteStrategy as SourceWriteStrategy


def loader(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    depends_on: tuple[Callable[..., object], ...] | list[Callable[..., object]] = (),
    destination: str | None = None,
    write_strategy: str | None = None,
    cursor_column: str | None = None,
    unique_key: str | Sequence[str] | None = None,
    columns: Sequence[LoaderColumnSpec | SourceColumnEntry] = (),
    contract: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild source loader."""

    return apply_loader(
        function=function,
        name=name,
        depends_on=depends_on,
        destination=destination,
        write_strategy=write_strategy,
        cursor_column=cursor_column,
        unique_key=unique_key,
        columns=columns,
        contract=contract,
    )


def get_loader_definition(function: Callable[..., object]) -> LoaderDefinition | None:
    """Return SQLBuild loader metadata from a decorated function, if present."""

    return read_loader_definition(function)
