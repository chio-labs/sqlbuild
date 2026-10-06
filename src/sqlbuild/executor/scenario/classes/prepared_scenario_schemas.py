"""Scenario schemas ensured once per invocation."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


class PreparedScenarioSchemas:
    """Thread-safe record of the scenario destination schemas already ensured."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._prepared: set[tuple[str | None, str]] = set()

    def ensure(
        self, *, scenario_plan: ScenarioExecutionPlan, adapter: BaseAdapter, connection: Any
    ) -> bool:
        """Ensure every schema the scenario writes to; return whether all are ready."""

        locations: tuple[CompiledRelationLocation, ...] = (
            *(fixture_plan.destination for fixture_plan in scenario_plan.fixture_plans),
            *(entry.destination for entry in scenario_plan.model_entries),
        )
        schemas: set[tuple[str | None, str]] = set()
        location: CompiledRelationLocation
        for location in locations:
            if location.schema is not None:
                schemas.add((location.database, location.schema))
        with self._lock:
            missing: list[tuple[str | None, str]] = sorted(
                schemas - self._prepared, key=lambda item: (item[0] or "", item[1])
            )
            database: str | None
            schema: str
            for database, schema in missing:
                try:
                    adapter.ensure_schema(
                        connection=connection,
                        database=database,
                        schema=schema,
                        statement_recorder=StatementRecorder(),
                    )
                except Exception as exc:
                    log_debug_event(
                        logger=_DEBUG_LOGGER,
                        message="scenario schema preparation failed; preparing per relation",
                        sqlbuild_error=str(exc),
                    )
                    return False
                self._prepared.add((database, schema))
            return True
