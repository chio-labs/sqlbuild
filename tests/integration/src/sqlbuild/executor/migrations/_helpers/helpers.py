"""Builders for migration executor helper integration tests."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.types import (
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
)
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry


def orders_migration_entry() -> ModelMigrationPlanEntry:
    """Return a planned forced replace of main.orders_v2 from main.orders."""

    return ModelMigrationPlanEntry(
        model_name="orders_v2",
        discovery=MigrationDiscovery.MANUAL,
        decision=MigrationDecision.FORCED_REPLACE,
        compatibility=MigrationCompatibility.COMPATIBLE,
        origin_model="orders",
        origin=CompiledRelationLocation(
            database=None, schema="main", name="orders", qualified_name="main.orders"
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name="orders_v2",
            qualified_name="main.orders_v2",
        ),
        target_name=None,
    )
