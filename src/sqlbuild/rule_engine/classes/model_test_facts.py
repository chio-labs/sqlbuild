"""SQL test facts for custom rules."""

from functools import cached_property

from sqlbuild._native import CompiledSqlTest, Model
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.rule_engine.types import RuleFactProject


class TestFacts:
    """Compiled SQL tests indexed by their model subject."""

    def __init__(self, *, project: RuleFactProject) -> None:
        self._project: RuleFactProject = project

    @cached_property
    def _tests(self) -> tuple[CompiledSqlTest, ...]:
        return self._project.sql_tests

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
