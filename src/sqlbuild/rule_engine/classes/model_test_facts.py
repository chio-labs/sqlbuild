"""SQL test facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.rule_engine.models import Model


class TestFacts:
    """Compiled SQL tests indexed by their model subject."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._tests: tuple[CompiledSqlTest, ...] = project.sql_tests
        by_model: dict[str, list[CompiledSqlTest]] = {}
        for test in self._tests:
            if test.mode is not SqlTestMode.MODEL:
                continue
            for model_name in dict.fromkeys(test.target_model_names):
                by_model.setdefault(model_name, []).append(test)
        self._by_model: dict[str, tuple[CompiledSqlTest, ...]] = {
            name: tuple(tests) for name, tests in by_model.items()
        }

    def all(self) -> tuple[CompiledSqlTest, ...]:
        return self._tests

    def for_model(self, model: Model) -> tuple[CompiledSqlTest, ...]:
        return self._by_model.get(model.name, ())
