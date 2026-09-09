"""SQL facts indexed by custom-rule model subjects."""

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine.classes.sql_document import SqlDocument
from sqlbuild.rule_engine.exceptions import RuleUsageError
from sqlbuild.rule_engine.models import Model, ModelSql


class SqlFacts:
    """Authored and expanded SQL indexed by public model identity."""

    def __init__(self, *, dialect: str, project: CompiledProject) -> None:
        self._dialect: str = dialect
        self._models: dict[object, CompiledModel] = {
            model.relative_path: model for model in project.models
        }
        self._documents: dict[object, ModelSql] = {}

    def for_model(self, model: Model) -> ModelSql:
        cached: ModelSql | None = self._documents.get(model.path)
        if cached is not None:
            return cached
        compiled: CompiledModel = self._resolve(model)
        documents: ModelSql = ModelSql(
            authored=SqlDocument(source=compiled.authored_sql, dialect=self._dialect),
            expanded=SqlDocument(source=compiled.query_sql, dialect=self._dialect),
        )
        self._documents[model.path] = documents
        return documents

    def _resolve(self, model: Model) -> CompiledModel:
        try:
            return self._models[model.path]
        except KeyError as error:
            raise RuleUsageError(f"model is not part of this project: {model.path}") from error
