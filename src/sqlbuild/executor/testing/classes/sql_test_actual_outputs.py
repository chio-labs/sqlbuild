"""Evaluate a unit test's tested chain once and let every comparison read the stored output."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any
from uuid import uuid4

from sqlbuild._native import SqlTestPlanEntry, render_sql_test_comparison_sql
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.diagnostics.classes.diagnostic_record_redactor import DiagnosticRecordRedactor
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.runtime.execution_limits.exceptions import (
    ExecutionDurationLimitError,
    ItemTimeoutError,
)
from sqlbuild.runtime.execution_limits.main.execution_deadlines_suspended import (
    execution_deadlines_suspended,
)

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")
_OUTPUT_PREFIX: str = "__sqb_test_output"


class SqlTestActualOutputs:
    """The actual outputs of one test's compared chain steps, stored once and dropped after."""

    def __init__(
        self, *, test_entry: SqlTestPlanEntry, adapter: BaseAdapter, connection: Any
    ) -> None:
        self._test_entry: SqlTestPlanEntry = test_entry
        self._adapter: BaseAdapter = adapter
        self._connection: Any = connection
        self._created: list[str] = []
        self.relations: dict[int, str] = {}

    def __enter__(self) -> SqlTestActualOutputs:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def materialize(self) -> dict[int, str]:
        """Store each compared step's output, or return no relations to compare inline."""

        token: str = uuid4().hex[:12]
        storing: int | None = None
        try:
            for index in range(len(self._test_entry.chain)):
                sql: str = self._output_sql(index=index, relations=dict(self.relations))
                if not sql:
                    continue
                storing = index
                relation: str | None = self._adapter.create_sql_test_output(
                    connection=self._connection,
                    sql=sql,
                    name=f"{_OUTPUT_PREFIX}_{token}_{index}",
                )
                storing = None
                if relation is None:
                    self.release()
                    return {}
                if relation.startswith(_OUTPUT_PREFIX):
                    self._created.append(relation)
                self.relations[index] = relation
        except (ItemTimeoutError, ExecutionDurationLimitError):
            raise
        except Exception as error:
            self.release()
            self._evaluate_output(index=storing, storage_error=error)
            log_debug_event(
                logger=_LOGGER,
                message="SQL test output could not be stored; comparing inline",
                test_name=self._test_entry.name,
                sqlbuild_error=DiagnosticRecordRedactor.text(str(error)),
            )
            return {}
        return dict(self.relations)

    def _output_sql(self, *, index: int, relations: dict[int, str]) -> str:
        """The SQL of step ``index``'s output, reading the given stored outputs of earlier steps."""

        (sql,) = render_sql_test_comparison_sql(
            (self._test_entry,),
            set_difference_operator=self._adapter.render_set_difference_operator(),
            sql_analysis_dialect=self._adapter.sql_analysis_dialect(),
            output_step_index=index,
            actual_relations=relations,
        )
        return sql

    def _evaluate_output(self, *, index: int | None, storage_error: Exception) -> None:
        """Run a step that could not be stored fully inline, raising the query's own error."""

        if index is None:
            return
        try:
            cursor: Any = self._adapter.execute(
                connection=self._connection, sql=self._output_sql(index=index, relations={})
            )
            _ = cursor.fetchall()
        except (ItemTimeoutError, ExecutionDurationLimitError):
            raise
        except Exception:
            log_debug_event(
                logger=_LOGGER,
                message="SQL test output could not be stored, and its query fails on its own",
                test_name=self._test_entry.name,
                sqlbuild_error=DiagnosticRecordRedactor.text(str(storage_error)),
            )
            raise

    def release(self) -> None:
        """Drop every stored output; later comparisons run inline."""

        created: list[str] = list(self._created)
        self._created.clear()
        self.relations.clear()
        with execution_deadlines_suspended():
            for relation in created:
                try:
                    self._adapter.drop_sql_test_output(
                        connection=self._connection, relation=relation
                    )
                except Exception as error:
                    log_debug_event(
                        logger=_LOGGER,
                        message="SQL test output cleanup failed",
                        test_name=self._test_entry.name,
                        sqlbuild_error=DiagnosticRecordRedactor.text(str(error)),
                    )
