"""SQL test facts for custom rules."""

from functools import cached_property

from sqlbuild.compiler.compile.models import CompiledSqlTest
from sqlbuild.compiler.compile.types import CompiledProjectView, SqlTestMode
from sqlbuild.rule_engine.models import Model


class TestFacts:
    """Compiled SQL tests indexed by their model subject."""

    def __init__(self, *, project: CompiledProjectView) -> None:
        self._tests: tuple[CompiledSqlTest, ...] = project.sql_tests

    @cached_property
    def _by_model(self) -> dict[str, tuple[CompiledSqlTest, ...]]:
        by_model: dict[str, list[CompiledSqlTest]] = {}
        for test in self._tests:
            if test.mode is not SqlTestMode.MODEL:
                continue
            for model_name in dict.fromkeys(test.target_model_names):
                by_model.setdefault(model_name, []).append(test)
        return {name: tuple(tests) for name, tests in by_model.items()}

    def all(self) -> tuple[CompiledSqlTest, ...]:
        return self._tests

    def for_model(self, model: Model) -> tuple[CompiledSqlTest, ...]:
        return self._by_model.get(model.name, ())
