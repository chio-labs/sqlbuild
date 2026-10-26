from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlbuild._native import (
    Model,
    RuleFactViews,
    build_compiled_project,
    compiled_model_record,
    compiled_project_record,
    discover_project_inputs,
)
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.rule_engine.classes.rule_context import build_rule_fact_views
from sqlbuild.rule_engine.types import RuleFactProject


class OrdersReferenceResolver:
    """External reference resolver that knows no extra relations."""

    def validate_model_names(self, *, known_model_names: set[str]) -> None:
        del known_model_names

    def extend_sql_test_model_names(self, *, known_model_names: set[str]) -> set[str]:
        return known_model_names

    def extend_sql_test_source_names(self, *, known_source_names: set[str]) -> set[str]:
        return known_source_names

    def extend_sql_test_seed_names(self, *, known_seed_names: set[str]) -> set[str]:
        return known_seed_names

    def validate_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
        owner_relative_sql_path: Path,
    ) -> None:
        del ref_kind, ref_name, ref_package, owner_relative_sql_path

    def resolve_reference(
        self, *, ref_kind: str, ref_name: str, ref_package: str | None
    ) -> str | None:
        del ref_kind, ref_name, ref_package
        return None


class ReferenceModel:
    """A compiled model read the way rule facts read full `CompiledModel` records."""

    def __init__(self, model: CompiledModelView) -> None:
        self._model: CompiledModelView = model
        self.name: str = model.name
        self.relative_path: Path = model.relative_path
        self.key: object = model.key
        self.deps: tuple[object, ...] = model.deps
        self.authored_sql: str = model.authored_sql
        self.query_sql: str = model.query_sql
        self.inferred_columns: object = model.inferred_columns
        self.enum_declarations: tuple[object, ...] = model.enum_declarations
        self.constant_declarations: tuple[object, ...] = model.constant_declarations
        self.declared_columns: tuple[object, ...] = getattr(model.schema_entry, "columns", ())
        self.enum_type_names: dict[str, str] = {
            column: declaration.name for column, declaration in model.enum_columns.items()
        }

    def config_value(self, name: str) -> object:
        return self._model.config.values.get(name)


class ReferenceProject:
    """A compiled project read the way rule facts read a full `CompiledProject` record."""

    def __init__(self, project: CompiledProjectView) -> None:
        self.models: tuple[ReferenceModel, ...] = tuple(map(ReferenceModel, project.models))
        self.effective_target_name: str | None = project.effective_target_name
        self.sources: tuple[object, ...] = project.sources
        self.seeds: tuple[object, ...] = project.seeds
        self.functions: tuple[object, ...] = project.functions
        self.audits: tuple[object, ...] = project.audits
        self.sql_tests: tuple[object, ...] = project.sql_tests
        self.public_enums: dict[str, object] = dict(project.public_enums)
        self.public_constants: dict[str, object] = dict(project.public_constants)


def compile_files(*, root: Path, files: dict[str, str]) -> CompiledProjectView:
    """Write and compile one DuckDB project with an external reference resolver."""

    for relative_path, contents in files.items():
        path: Path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return build_compiled_project(
        discovered_inputs=discover_project_inputs(project_dir=root),
        adapter=DuckDbAdapter(),
        external_sql_reference_resolver=OrdersReferenceResolver(),
    )


def fact_views(*, project: RuleFactProject, root: Path) -> RuleFactViews:
    """Build the fact views one host evaluation reads through."""

    return build_rule_fact_views(project=project, project_dir=root, dialect="duckdb")


def native_project(project: CompiledProjectView) -> CompiledProjectView:
    """The compiled project as the compiler built it."""

    return project


def record_project(project: CompiledProjectView) -> CompiledProjectView:
    """The compiled project as a `CompiledProject` record holding `CompiledModel` records."""

    record: Any = compiled_project_record(project)
    return replace(record, models=tuple(map(compiled_model_record, record.models)))


def every_fact_value(views: RuleFactViews) -> dict[str, object]:
    """Read every public fact once, keyed by fact and subject."""

    values: dict[str, object] = {
        "project.models": views.project.models,
        "project.sources": views.project.sources,
        "project.seeds": views.project.seeds,
        "project.functions": views.project.functions,
        "project.tests": views.project.tests,
        "project.audits": views.project.audits,
        "tests.all": views.tests.all(),
        "audits.all": views.audits.all(),
        "declarations.public_enums": views.declarations.public_enums,
        "declarations.public_constants": views.declarations.public_constants,
        "declarations.enums": views.declarations.enums,
        "declarations.constants": views.declarations.constants,
        "tree.resources_under": views.project.tree.resources_under("models"),
    }
    model: Model
    for model in views.project.models:
        subject: str = model.path.as_posix()
        documents: Any = views.sql.for_model(model)
        values[f"sql.for_model:{subject}"] = (documents.authored.source, documents.expanded.source)
        values[f"graph.dependencies:{subject}"] = views.graph.dependencies(model)
        values[f"graph.dependents:{subject}"] = views.graph.dependents(model)
        values[f"columns.declared:{subject}"] = views.columns.declared(model)
        values[f"columns.inferred:{subject}"] = views.columns.inferred(model)
        values[f"columns.names:{subject}"] = views.columns.names(model)
        values[f"columns.enum_types:{subject}"] = views.columns.enum_types(model)
        values[f"contracts.enforced:{subject}"] = views.contracts.enforced(model)
        values[f"contracts.grain:{subject}"] = views.contracts.grain(model)
        values[f"tests.for_model:{subject}"] = views.tests.for_model(model)
        values[f"audits.for_model:{subject}"] = views.audits.for_model(model)
    return values
