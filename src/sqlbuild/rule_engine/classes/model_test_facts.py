"""SQL test facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.rule_engine.models import Model


class TestFacts:
    """Compiled SQL tests indexed by their model subject."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._tests: tuple[CompiledSqlTest, ...] = project.sql_tests

    def all(self) -> tuple[CompiledSqlTest, ...]:
        return self._tests

    def for_model(self, model: Model) -> tuple[CompiledSqlTest, ...]:
        return tuple(
            test
            for test in self._tests
            if test.mode is SqlTestMode.MODEL and model.name in test.target_model_names
        )
