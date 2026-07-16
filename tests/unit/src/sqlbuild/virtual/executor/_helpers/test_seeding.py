from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import PlanAction
from sqlbuild.virtual.executor._helpers.seeding import (
    _seed_physical_relation,
    seed_virtual_physical_version,
)
from sqlbuild.virtual.state.models import PhysicalRelationAncestryRecord, PhysicalRelationRecord
from sqlbuild.virtual.state.types import PhysicalArtifactType
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    SeedingIdempotencyTestCase,
    SeedingStrategyTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor._helpers.helpers import (
    build_seeded_incremental_plan_output,
)


class FakeSeedAdapter(BaseAdapter):
    def __init__(self, *, supports_durable_clone: bool, target_exists: bool = False) -> None:
        self._supports_durable_clone = supports_durable_clone
        self._target_exists = target_exists
        self.executed_sql: list[str] = []
        self.drop_count: int = 0

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        return object()

    def close(self, connection: object) -> None:
        del connection

    def supports_durable_clone(self) -> bool:
        return self._supports_durable_clone

    def render_durable_clone(
        self, *, origin: str, destination: str, origin_is_transient: bool = False
    ) -> tuple[str, ...]:
        del origin_is_transient
        return (f"CREATE TABLE {destination} DEEP CLONE {origin}",)

    def relation_exists(
        self,
        connection: object,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        del connection, database, schema, name
        return self._target_exists

    def list_relations(
        self,
        connection: object,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection, database, schemas, names
        return ()

    def ensure_schema(
        self,
        connection: object,
        *,
        database: str | None,
        schema: str | None,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, database, schema, statement_recorder

    def drop(
        self,
        connection: object,
        *,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists, statement_recorder
        self.drop_count += 1
        self.executed_sql.append(f"DROP {destination}")


class FakeStateBackend:
    def __init__(self) -> None:
        self.ancestry_records: list[PhysicalRelationAncestryRecord] = []

    def upsert_physical_relation_ancestry(
        self,
        connection: object,
        *,
        schema: str,
        record: PhysicalRelationAncestryRecord,
    ) -> None:
        del connection, schema
        self.ancestry_records.append(record)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedingStrategyTestCase(
            description="uses durable clone when adapter supports it",
            incremental_strategy="delete_insert",
            supports_durable_clone=True,
            expected_strategy="durable_clone",
            expected_sql_fragment="DEEP CLONE source_relation",
        ),
        SeedingStrategyTestCase(
            description="uses copy when adapter lacks durable clone",
            incremental_strategy="delete_insert",
            supports_durable_clone=False,
            expected_strategy="copy",
            expected_sql_fragment="SELECT * FROM source_relation",
        ),
        SeedingStrategyTestCase(
            description="uses bounded append copy before durable clone",
            incremental_strategy="append",
            supports_durable_clone=True,
            expected_strategy="bounded_append_copy",
            expected_sql_fragment='WHERE "ordered_at" < TIMESTAMP',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_seed_context_when_seeding_then_selects_expected_strategy(
    test_case: SeedingStrategyTestCase,
) -> None:
    adapter: FakeSeedAdapter = FakeSeedAdapter(
        supports_durable_clone=test_case.supports_durable_clone
    )
    entry: ModelPlanEntry = build_seeded_incremental_plan_output(
        incremental_strategy=test_case.incremental_strategy
    ).model_entries[0]

    strategy: str = _seed_physical_relation(
        adapter=adapter,
        connection=object(),
        origin="source_relation",
        destination="target_relation",
        entry=entry,
        origin_is_transient=False,
        statement_recorder=StatementRecorder(),
    )

    assert strategy == test_case.expected_strategy
    assert any(test_case.expected_sql_fragment in sql for sql in adapter.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedingIdempotencyTestCase(
            description="drops existing target before seeding",
            target_exists=True,
            expected_drop_count=1,
            expected_ancestry_count=1,
            expected_first_sql_prefix="DROP ",
        ),
        SeedingIdempotencyTestCase(
            description="seeds missing target without drop",
            target_exists=False,
            expected_drop_count=0,
            expected_ancestry_count=1,
            expected_first_sql_prefix="CREATE OR REPLACE TABLE ",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_target_when_seeding_then_existing_target_is_dropped_first(
    test_case: SeedingIdempotencyTestCase,
) -> None:
    adapter: FakeSeedAdapter = FakeSeedAdapter(
        supports_durable_clone=False,
        target_exists=test_case.target_exists,
    )
    backend: FakeStateBackend = FakeStateBackend()
    entry: ModelPlanEntry = build_seeded_incremental_plan_output(
        incremental_strategy="delete_insert",
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
    ).model_entries[0]
    parent_relation: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
        version_hash="oldhash",
        database_name="",
        schema_name="dev__sqb_physical",
        relation_name="orders__v_oldhash",
        relation_type="table",
    )

    seed_virtual_physical_version(
        adapter=adapter,
        connection=object(),
        backend=backend,
        state_connection=object(),
        state_schema="sqlbuild_state",
        entry=entry,
        parent_relation=parent_relation,
        version_hash="newhash",
    )

    assert adapter.drop_count == test_case.expected_drop_count
    assert len(backend.ancestry_records) == test_case.expected_ancestry_count
    assert adapter.executed_sql[0].startswith(test_case.expected_first_sql_prefix)
