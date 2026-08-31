from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.models import ArchiveEvent
from sqlbuild.archives.types import ArchiveRecordType
from sqlbuild.executor.run._helpers.execution import permanent_promotion
from sqlbuild.executor.run._helpers.execution.permanent_promotion import (
    build_permanent_promotion_requirement,
    promote_permanent_relation,
)
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    PermanentArchiveConflictTestCase,
    PermanentPromotionTestCase,
    PermanentRequirementTestCase,
)


class _FakeStore:
    def __init__(self, *, history: list[ArchiveEvent], timeline: list[str]) -> None:
        self.history = history
        self.timeline = timeline

    def read_target_history(
        self, *, database: str | None, schema: str, target_name: str
    ) -> tuple[ArchiveEvent, ...]:
        del database, schema, target_name
        return tuple(self.history)

    def write(self, event: ArchiveEvent) -> None:
        if not any(existing.event_id == event.event_id for existing in self.history):
            self.history.append(event)
        self.timeline.append(event.record_type.value)


class _FakePermanentAdapter:
    def __init__(
        self,
        *,
        relations: dict[str, RelationInfo],
        timeline: list[str],
        archive_completed_at: datetime,
    ) -> None:
        self.relations = relations
        self.timeline = timeline
        self.archive_completed_at = archive_completed_at

    def maximum_identifier_length(self) -> int:
        return 255

    def render_qualified_name(self, *, database: str | None, schema: str | None, name: str) -> str:
        del database
        return f"{schema}.{name}"

    def list_relations(
        self,
        *,
        connection: Any,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection, database, schemas
        return tuple(self.relations[name] for name in names or () if name in self.relations)

    def rename(
        self,
        *,
        connection: Any,
        origin: str,
        destination: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection
        origin_name: str = origin.rsplit(".", 1)[-1]
        destination_name: str = destination.rsplit(".", 1)[-1]
        relation: RelationInfo = self.relations.pop(origin_name)
        if destination_name.startswith("__sqb_archive__"):
            relation = replace(relation, last_altered_at=self.archive_completed_at)
            action = "rename_archive"
        else:
            action = "rename_target"
        self.relations[destination_name] = replace(relation, name=destination_name)
        self.timeline.append(action)
        statement_recorder.record_many((f"RENAME {origin} TO {destination}",))

    def drop(
        self,
        *,
        connection: Any,
        destination: str,
        if_exists: bool,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists
        name: str = destination.rsplit(".", 1)[-1]
        self.relations.pop(name, None)
        self.timeline.append("drop_staging")
        statement_recorder.record_many((f"DROP {destination}",))


_SOURCE_CREATED_AT: datetime = datetime(2026, 8, 1, 2, 3, 4, tzinfo=UTC)
_ARCHIVE_COMPLETED_AT: datetime = _SOURCE_CREATED_AT + timedelta(days=30)


@pytest.mark.parametrize(
    "test_case",
    [
        PermanentRequirementTestCase(
            description="different runtime runs produce byte-equivalent migration requirement",
            source_created_at=_SOURCE_CREATED_AT,
            expected_operation_kind="table_type_migration",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_source_generation_when_building_requirement_then_payload_is_deterministic(
    test_case: PermanentRequirementTestCase,
) -> None:
    target: RelationInfo = RelationInfo(
        database="racing",
        schema="mart",
        name="orders",
        relation_type="base table",
        created_at=test_case.source_created_at,
        is_transient=True,
    )
    first: ArchiveEvent = build_permanent_promotion_requirement(
        adapter=SnowflakeAdapter(),
        target=target,
        target_database="racing",
        target_schema="mart",
        target_name="orders",
        operation_identity="model-version-a",
    )
    second: ArchiveEvent = build_permanent_promotion_requirement(
        adapter=SnowflakeAdapter(),
        target=target,
        target_database="racing",
        target_schema="mart",
        target_name="orders",
        operation_identity="model-version-a",
    )

    assert first == second
    assert first.event_id == second.event_id
    assert first.origin_run_id == "model-version-a"
    assert first.execution_run_id == "model-version-a"
    assert first.operation_kind == test_case.expected_operation_kind


@pytest.mark.parametrize(
    "test_case",
    [
        PermanentPromotionTestCase(
            description="existing target archives before permanent promotion",
            initial_state="existing",
            operation_identity="model-version-a",
            expected_timeline=(
                "requirement",
                "rename_archive",
                "completion",
                "rename_target",
            ),
            expected_completion_time=_ARCHIVE_COMPLETED_AT,
        ),
        PermanentPromotionTestCase(
            description="retry after archive rename replays completion then promotes",
            initial_state="renamed",
            operation_identity="model-version-a",
            expected_timeline=("completion", "rename_target"),
            expected_completion_time=_ARCHIVE_COMPLETED_AT,
        ),
        PermanentPromotionTestCase(
            description="response loss after promotion converges without another archive",
            initial_state="promoted",
            operation_identity="model-version-a",
            expected_timeline=("drop_staging",),
            expected_completion_time=_ARCHIVE_COMPLETED_AT,
        ),
        PermanentPromotionTestCase(
            description="later distinct build archives the current permanent target",
            initial_state="promoted",
            operation_identity="model-version-b",
            expected_timeline=(
                "requirement",
                "rename_archive",
                "completion",
                "rename_target",
            ),
            expected_completion_time=_ARCHIVE_COMPLETED_AT,
        ),
        PermanentPromotionTestCase(
            description="missing target directly renames permanent staging",
            initial_state="missing",
            operation_identity="model-version-a",
            expected_timeline=("rename_target",),
            expected_completion_time=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_physical_retry_state_when_promoting_permanent_then_reconciles_in_order(
    test_case: PermanentPromotionTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeline: list[str] = []
    target: RelationInfo = RelationInfo(
        database="racing",
        schema="mart",
        name="orders",
        relation_type="base table",
        created_at=_SOURCE_CREATED_AT,
        last_altered_at=_SOURCE_CREATED_AT,
        is_transient=True,
    )
    staging: RelationInfo = replace(
        target,
        name="orders__staging",
        created_at=_SOURCE_CREATED_AT + timedelta(days=1),
        is_transient=False,
    )
    adapter: _FakePermanentAdapter = _FakePermanentAdapter(
        relations={}, timeline=timeline, archive_completed_at=_ARCHIVE_COMPLETED_AT
    )
    requirement: ArchiveEvent = build_permanent_promotion_requirement(
        adapter=cast(Any, adapter),
        target=target,
        target_database="racing",
        target_schema="mart",
        target_name="orders",
        operation_identity="model-version-a",
    )
    archive: RelationInfo = replace(
        target, name=requirement.archive_name, last_altered_at=_ARCHIVE_COMPLETED_AT
    )
    completion: ArchiveEvent = replace(
        requirement,
        event_id=permanent_promotion.build_archive_event_id(
            requirement_id=requirement.requirement_id,
            record_type=ArchiveRecordType.COMPLETION,
        ),
        record_type=ArchiveRecordType.COMPLETION,
        archive_physical_generation=_SOURCE_CREATED_AT.isoformat(),
        completed_at=_ARCHIVE_COMPLETED_AT,
        observed_at=_ARCHIVE_COMPLETED_AT,
        created_at=_ARCHIVE_COMPLETED_AT,
    )
    promoted_relations: dict[str, RelationInfo] = {
        requirement.archive_name: archive,
        "orders": replace(staging, name="orders"),
        "orders__staging": replace(staging, created_at=_SOURCE_CREATED_AT + timedelta(days=2)),
    }
    relations_by_state: dict[str, dict[str, RelationInfo]] = {
        "existing": {"orders": target, "orders__staging": staging},
        "renamed": {requirement.archive_name: archive, "orders__staging": staging},
        "promoted": promoted_relations,
        "missing": {"orders__staging": staging},
    }
    history_by_state: dict[str, list[ArchiveEvent]] = {
        "existing": [],
        "renamed": [requirement],
        "promoted": [requirement, completion],
        "missing": [],
    }
    adapter.relations.update(relations_by_state[test_case.initial_state])
    history: list[ArchiveEvent] = history_by_state[test_case.initial_state]
    store: _FakeStore = _FakeStore(history=history, timeline=timeline)
    monkeypatch.setattr(
        permanent_promotion,
        "DirectArchiveEventStore",
        lambda **kwargs: store,
    )

    promote_permanent_relation(
        adapter=cast(Any, adapter),
        connection=object(),
        staging_relation="mart.orders__staging",
        staging_name="orders__staging",
        destination_relation="mart.orders",
        destination_database="racing",
        destination_schema="mart",
        destination_name="orders",
        operation_identity=test_case.operation_identity,
        statement_recorder=StatementRecorder(),
    )

    assert tuple(timeline) == test_case.expected_timeline
    assert adapter.relations["orders"].is_transient is False
    assert not hasattr(adapter, "transaction")
    assert not hasattr(adapter, "lock")
    completion_times: dict[ArchiveRecordType, datetime | None] = {
        event.record_type: event.completed_at for event in store.history
    }
    assert completion_times.get(ArchiveRecordType.COMPLETION) == test_case.expected_completion_time


@pytest.mark.parametrize(
    "test_case",
    [
        PermanentArchiveConflictTestCase(
            description="both target and archive present fails closed",
            archive_generation_offset_seconds=0,
            expected_error_fragment="both contain the source generation",
        ),
        PermanentArchiveConflictTestCase(
            description="archive generation conflict fails closed",
            archive_generation_offset_seconds=1,
            expected_error_fragment="conflicts with safety requirement",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_archive_state_when_promoting_permanent_then_fails_closed(
    test_case: PermanentArchiveConflictTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeline: list[str] = []
    target: RelationInfo = RelationInfo(
        database="racing",
        schema="mart",
        name="orders",
        relation_type="base table",
        created_at=_SOURCE_CREATED_AT,
        last_altered_at=_SOURCE_CREATED_AT,
        is_transient=False,
    )
    adapter: _FakePermanentAdapter = _FakePermanentAdapter(
        relations={"orders": target},
        timeline=timeline,
        archive_completed_at=_ARCHIVE_COMPLETED_AT,
    )
    requirement: ArchiveEvent = build_permanent_promotion_requirement(
        adapter=cast(Any, adapter),
        target=target,
        target_database="racing",
        target_schema="mart",
        target_name="orders",
        operation_identity="model-version-a",
    )
    archive_created_at: datetime = _SOURCE_CREATED_AT + timedelta(
        seconds=test_case.archive_generation_offset_seconds
    )
    adapter.relations[requirement.archive_name] = replace(
        target, name=requirement.archive_name, created_at=archive_created_at
    )
    store: _FakeStore = _FakeStore(history=[], timeline=timeline)
    monkeypatch.setattr(
        permanent_promotion,
        "DirectArchiveEventStore",
        lambda **kwargs: store,
    )

    with pytest.raises(ArchiveStateError) as exc_info:
        promote_permanent_relation(
            adapter=cast(Any, adapter),
            connection=object(),
            staging_relation="mart.orders__staging",
            staging_name="orders__staging",
            destination_relation="mart.orders",
            destination_database="racing",
            destination_schema="mart",
            destination_name="orders",
            operation_identity="model-version-a",
            statement_recorder=StatementRecorder(),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
