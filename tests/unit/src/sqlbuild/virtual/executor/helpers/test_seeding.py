from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.virtual.executor.helpers.seeding import _seed_physical_relation
from tests.unit.src.sqlbuild.virtual.executor.helpers._test_types import SeedingStrategyTestCase
from tests.unit.src.sqlbuild.virtual.executor.helpers.helpers import (
    build_seeded_incremental_plan_output,
)


class FakeSeedAdapter(BaseAdapter):
    def __init__(self, *, supports_durable_clone: bool) -> None:
        self._supports_durable_clone = supports_durable_clone
        self.executed_sql: list[str] = []

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

    def render_durable_clone(self, *, source: str, target: str) -> tuple[str, ...]:
        return (f"CREATE TABLE {target} DEEP CLONE {source}",)


TEST_CASES: list[SeedingStrategyTestCase] = [
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
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
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
        source="source_relation",
        target="target_relation",
        entry=entry,
        statement_recorder=StatementRecorder(),
    )

    assert strategy == test_case.expected_strategy
    assert any(test_case.expected_sql_fragment in sql for sql in adapter.executed_sql)
