"""Own speculative SQL checks for one compilation invocation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import TracebackType

from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.rule_engine.main._prepare_sql_rules import prepare_sql_rules
from sqlbuild.rule_engine.models import PreparedSqlLint


class EarlySqlLint:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled: bool = enabled
        self.preparation: PreparedSqlLint | None = None
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
        self.executor.shutdown(wait=True, cancel_futures=True)

    def start(self, *, inputs: CompileProjectInputs, dialect: str) -> None:
        if self.enabled:
            self.preparation = prepare_sql_rules(
                inputs=inputs, executor=self.executor, dialect=dialect
            )
