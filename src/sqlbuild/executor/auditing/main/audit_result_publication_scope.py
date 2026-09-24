"""Incremental audit completion publication scope entrypoint."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing._helpers.result_projection import (
    audit_result_publication_scope_impl,
)


@contextmanager
def audit_result_publication_scope(
    *,
    plan: PlanOutput,
    storage_database: str | None = None,
    storage_schema: str | None = None,
) -> Iterator[None]:
    """Publish audit completions as they are confirmed until the batch projection runs."""

    with audit_result_publication_scope_impl(
        plan=plan,
        storage_database=storage_database,
        storage_schema=storage_schema,
    ):
        yield
