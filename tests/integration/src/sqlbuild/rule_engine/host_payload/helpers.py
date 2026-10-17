import dataclasses
from itertools import product
from pathlib import Path

from sqlbuild._native import (
    Model,
    build_compiled_project,
    custom_rule_fact_digest,
    discover_project_inputs,
)
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.constants import (
    FACT_AUDITS_ALL,
    FACT_AUDITS_FOR_MODEL,
    FACT_COLUMNS_DECLARED,
    FACT_COLUMNS_INFERRED,
    FACT_COLUMNS_NAMES,
    FACT_CONTRACTS_ENFORCED,
    FACT_CONTRACTS_GRAIN,
    FACT_DECLARATIONS_CONSTANTS,
    FACT_DECLARATIONS_ENUMS,
    FACT_DECLARATIONS_PUBLIC_CONSTANTS,
    FACT_DECLARATIONS_PUBLIC_ENUMS,
    FACT_GRAPH_DEPENDENCIES,
    FACT_GRAPH_DEPENDENTS,
    FACT_PROJECT_AUDITS,
    FACT_PROJECT_FUNCTIONS,
    FACT_PROJECT_MODELS,
    FACT_PROJECT_SEEDS,
    FACT_PROJECT_SOURCES,
    FACT_PROJECT_TESTS,
    FACT_SQL_FOR_MODEL,
    FACT_TESTS_ALL,
    FACT_TESTS_FOR_MODEL,
    FACT_TREE_CHILDREN,
    FACT_TREE_DESCENDANTS,
    FACT_TREE_GLOB,
    FACT_TREE_PATHS,
    FACT_TREE_READ_TEXT,
    FACT_TREE_RELATIVE_PARTS,
    FACT_TREE_RESOURCES_UNDER,
)
from sqlbuild.rule_engine.types import FactKey

_TREE_ARGUMENTS: tuple[str, ...] = ("models/marts/order_totals.sql", "models")
_GLOBAL_FACTS: tuple[str, ...] = (
    FACT_PROJECT_MODELS,
    FACT_PROJECT_SOURCES,
    FACT_PROJECT_SEEDS,
    FACT_PROJECT_FUNCTIONS,
    FACT_PROJECT_TESTS,
    FACT_PROJECT_AUDITS,
    FACT_TREE_PATHS,
    FACT_TESTS_ALL,
    FACT_AUDITS_ALL,
    FACT_DECLARATIONS_PUBLIC_ENUMS,
    FACT_DECLARATIONS_PUBLIC_CONSTANTS,
    FACT_DECLARATIONS_ENUMS,
    FACT_DECLARATIONS_CONSTANTS,
)
_MODEL_PATH_FACTS: tuple[str, ...] = (
    FACT_SQL_FOR_MODEL,
    FACT_GRAPH_DEPENDENCIES,
    FACT_GRAPH_DEPENDENTS,
    FACT_COLUMNS_DECLARED,
    FACT_COLUMNS_INFERRED,
    FACT_COLUMNS_NAMES,
    FACT_CONTRACTS_ENFORCED,
    FACT_CONTRACTS_GRAIN,
)
_MODEL_NAME_FACTS: tuple[str, ...] = (FACT_TESTS_FOR_MODEL, FACT_AUDITS_FOR_MODEL)
_TEXT_FACTS: tuple[tuple[str, int], ...] = (
    (FACT_TREE_CHILDREN, 1),
    (FACT_TREE_DESCENDANTS, 1),
    (FACT_TREE_GLOB, 1),
    (FACT_TREE_RELATIVE_PARTS, 2),
    (FACT_TREE_RESOURCES_UNDER, 1),
    (FACT_TREE_READ_TEXT, 1),
)


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


def dropped_fields(*, before: object, after: object) -> frozenset[str]:
    """Return the fields of `after`'s dataclass whose values differ between the two snapshots."""

    names: tuple[str, ...] = tuple(field.name for field in dataclasses.fields(type(after)))
    return frozenset(filter(lambda name: getattr(before, name) != getattr(after, name), names))


def every_fact_key(project: CompiledProjectView) -> tuple[FactKey, ...]:
    """Return a key for every fact Rules can read, over every model of the project."""

    models: tuple[Model, ...] = tuple(public_model(model) for model in project.models)
    return (
        *((fact,) for fact in _GLOBAL_FACTS),
        *((fact, model.path.as_posix()) for fact, model in product(_MODEL_PATH_FACTS, models)),
        *((fact, model.name) for fact, model in product(_MODEL_NAME_FACTS, models)),
        *((fact, *_TREE_ARGUMENTS[:arity]) for fact, arity in _TEXT_FACTS),
    )


def fact_digests(*, project: CompiledProjectView, root: Path) -> dict[FactKey, str | None]:
    """Digest every fact the custom-rule cache can key a result on."""

    return {
        key: custom_rule_fact_digest(project=project, project_dir=root, key=key)
        for key in every_fact_key(project)
    }
