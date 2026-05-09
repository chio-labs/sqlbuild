from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import ScenarioFixturePlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind


class ScenarioFixtureTestAdapter(BaseAdapter):
    """Adapter that records scenario fixture materialization calls."""

    def __init__(self, *, fail_on_target: str | None = None) -> None:
        self.fail_on_target: str | None = fail_on_target
        self.executed_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        if self.fail_on_target is not None and self.fail_on_target in sql:
            raise RuntimeError(f"failed target {self.fail_on_target}")
        return object()

    def close(self, connection: object) -> None:
        del connection


def build_scenario_fixture_plan(
    *,
    kind: ScenarioArtifactKind = ScenarioArtifactKind.SOURCE,
    logical_name: str = "raw__orders",
    target_name: str = "__sqb_51b385aebe20__source__raw__orders",
    sql: str = "WITH helper_orders AS (SELECT 1 AS order_id) SELECT * FROM helper_orders",
) -> ScenarioFixturePlan:
    return ScenarioFixturePlan(
        kind=kind,
        logical_name=logical_name,
        target=CompiledRelationTarget(
            database=None,
            schema="scenario_schema",
            name=target_name,
            qualified_name=f"scenario_schema.{target_name}",
        ),
        sql=sql,
    )


def executed_create_table_sql(adapter: ScenarioFixtureTestAdapter) -> tuple[str, ...]:
    return tuple(sql for sql in adapter.executed_sql if "CREATE OR REPLACE TABLE" in sql)
