"""Builders for migration executor helper integration tests."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import MigrationStagePlan
from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.types import (
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
)
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry
from sqlbuild.executor.migrations.models import MigrationArtifactNames


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


class CloneRefusingDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter whose stage clone is scripted to fail with a copy fallback."""

    def __init__(
        self, *, clone_statements: tuple[str, ...], refused_messages: tuple[str, ...]
    ) -> None:
        super().__init__()
        self.clone_statements: tuple[str, ...] = clone_statements
        self.refused_messages: tuple[str, ...] = refused_messages

    def render_migration_stage(
        self,
        *,
        origin: str,
        stage: str,
        origin_is_transient: bool = False,
        stage_is_transient: bool | None = None,
    ) -> MigrationStagePlan:
        del origin_is_transient, stage_is_transient
        return MigrationStagePlan(
            transfer=MigrationTransfer.CLONE,
            statements=tuple(
                statement.format(stage=stage, origin=origin) for statement in self.clone_statements
            ),
            fallback_statements=(f"CREATE TABLE {stage} AS SELECT * FROM {origin}",),
            is_clone_refusal=self.is_clone_refusal,
        )

    def is_clone_refusal(self, error: BaseException) -> bool:
        """Treat errors naming one of the scripted refusal messages as clone refusals."""

        return any(message in str(error) for message in self.refused_messages)


def artifact_names_for(*, stage_name: str) -> MigrationArtifactNames:
    """Return artifact names for a fresh stage beside main.orders_v2."""

    return MigrationArtifactNames(
        stage_name=stage_name,
        stage_qualified=f"main.{stage_name}",
        displaced_name="_sqb_archive__20260102t030405z__migration_previous__orders_v2",
        displaced_qualified="main._sqb_archive__20260102t030405z__migration_previous__orders_v2",
        destination_qualified="main.orders_v2",
        destination_exists=False,
    )
