"""Own speculative SQL checks for one compilation invocation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import TracebackType

from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.rule_engine.main._prepare_sql_rules import prepare_sql_rules
from sqlbuild.rule_engine.models import PreparedSqlLint, SqlExpansionReuse


class EarlySqlLint:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled: bool = enabled
        self.preparation: PreparedSqlLint | None = None
        self.expansion_reuse: SqlExpansionReuse | None = None
        self.stop_requested: Event = Event()
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sqlbuild-lint"
        )

    def __enter__(self) -> EarlySqlLint:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = self.stop()

    def start(self, *, inputs: CompileProjectInputs, dialect: str) -> None:
        if self.enabled:
            self.preparation = prepare_sql_rules(
                inputs=inputs,
                executor=self.executor,
                dialect=dialect,
                stop=self.stop_requested,
            )
            self.expansion_reuse = (
                None
                if inputs.declaration_scope is None
                else SqlExpansionReuse(
                    discovered_inputs=inputs.discovered_inputs,
                    declaration_scope=inputs.declaration_scope,
                )
            )

    def stop(self) -> int:
        """Abandon unconsumed speculative work and return the milliseconds spent joining it."""

        stop_start: float = time.monotonic()
        self.stop_requested.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
        return int((time.monotonic() - stop_start) * 1000)
