"""SQL facts indexed by custom-rule model subjects."""

from functools import cached_property

from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.rule_engine.classes.sql_document import SqlDocument
from sqlbuild.rule_engine.exceptions import RuleUsageError
from sqlbuild.rule_engine.models import Model, ModelSql


class SqlFacts:
    """Authored and expanded SQL indexed by public model identity."""

    def __init__(self, *, dialect: str, project: CompiledProjectView) -> None:
        self._dialect: str = dialect
        self._project: CompiledProjectView = project
        self._documents: dict[object, ModelSql] = {}

    @cached_property
    def _models(self) -> dict[object, CompiledModelView]:
        return {model.relative_path: model for model in self._project.models}

    def for_model(self, model: Model) -> ModelSql:
        cached: ModelSql | None = self._documents.get(model.path)
        if cached is not None:
            return cached
        compiled: CompiledModelView = self._resolve(model)
        documents: ModelSql = ModelSql(
            authored=SqlDocument(source=compiled.authored_sql, dialect=self._dialect),
            expanded=SqlDocument(source=compiled.query_sql, dialect=self._dialect),
        )
        self._documents[model.path] = documents
        return documents

    def _resolve(self, model: Model) -> CompiledModelView:
        try:
            return self._models[model.path]
        except KeyError as error:
            raise RuleUsageError(f"model is not part of this project: {model.path}") from error
