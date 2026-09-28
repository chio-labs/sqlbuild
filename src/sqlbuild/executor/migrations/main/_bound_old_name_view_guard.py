"""Guard compatibility views bound to a model's relation while the build replaces or alters it."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from functools import partial
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.migrations._helpers.old_name_views import (
    drop_old_name_views,
    rebind_old_name_views,
    views_reading,
)
from sqlbuild.executor.migrations.models import OldNameViewSource
from sqlbuild.executor.run.models import BoundViewGuard


def bound_old_name_view_guard(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    destination: CompiledRelationLocation,
) -> BoundViewGuard:
    """Return the guard a materialization runs its promotion or column changes inside."""

    if not adapter.views_bind_to_relation_identity():
        return BoundViewGuard()
    sources: tuple[OldNameViewSource, ...] = views_reading(
        location=destination, recorded_views=plan.old_name_views
    )
    if not sources:
        return BoundViewGuard()
    transaction: partial[AbstractContextManager[object]] = partial(adapter.transaction, connection)
    return BoundViewGuard(
        transaction=transaction if adapter.supports_transactional_ddl() else nullcontext,
        release=partial(
            drop_old_name_views, adapter=adapter, connection=connection, sources=sources
        ),
        rebind=partial(
            rebind_old_name_views, adapter=adapter, connection=connection, sources=sources
        ),
    )
