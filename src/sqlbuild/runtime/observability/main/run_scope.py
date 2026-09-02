"""Run identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import run_scope as _run_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def run_scope(run_id: str) -> Iterator[ExecutionIdentity]:
    """Install a run while preserving or creating its invocation identity."""

    with _run_scope(run_id) as identity:
        yield identity
