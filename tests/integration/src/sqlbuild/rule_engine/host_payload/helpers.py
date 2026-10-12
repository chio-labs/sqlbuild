import dataclasses
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from sqlbuild._native import discover_project_inputs
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.rule_engine._helpers.engine import custom_rules, fact_replay
from sqlbuild.rule_engine._helpers.engine.fact_replay import (
    fact_outcome_digest,
    shared_fact_encoder,
)
from sqlbuild.rule_engine._helpers.host import custom_host_pool
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.classes.rule_context import RuleFactViews, build_rule_fact_views
from sqlbuild.rule_engine.models import Model
from sqlbuild.rule_engine.types import FactKey

_TREE_ARGUMENTS: tuple[str, ...] = ("models/marts/order_totals.sql", "models")


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
    return compile_project(
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
        *((fact,) for fact in fact_replay._GLOBAL_FACTS),
        *(
            (fact, model.path.as_posix())
            for fact, model in product(fact_replay._MODEL_PATH_FACTS, models)
        ),
        *((fact, model.name) for fact, model in product(fact_replay._MODEL_NAME_FACTS, models)),
        *(
            (fact, *_TREE_ARGUMENTS[: fact_replay._TEXT_FACT_ARITY[fact]])
            for fact in fact_replay._TEXT_FACTS
        ),
    )


def fact_digests(*, project: CompiledProjectView, root: Path) -> dict[FactKey, tuple[str, str]]:
    """Digest every fact as hosts observe it and as whole-project digests encode it."""

    views: RuleFactViews = build_rule_fact_views(
        project=project, project_dir=root, dialect="duckdb"
    )
    return {
        key: (
            fact_outcome_digest(views=views, key=key),
            fact_outcome_digest(views=views, key=key, shared=shared_fact_encoder()),
        )
        for key in every_fact_key(project)
    }


def record_trimmed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[type[object], set[str]]:
    """Record replaced fields and omitted constructor fields in the host-payload trimmers."""

    trimmed: dict[type[object], set[str]] = {CompiledProject: set(), CompiledModel: set()}

    def recording_replace(obj: Any, /, **changes: object) -> Any:
        trimmed.setdefault(type(obj), set()).update(changes)
        return dataclasses.replace(obj, **changes)

    def recording_model(**values: Any) -> CompiledModel:
        trimmed[CompiledModel].update(
            {field.name for field in dataclasses.fields(CompiledModel)} - values.keys()
        )
        return CompiledModel(**values)

    monkeypatch.setattr(custom_rules, "replace", recording_replace)
    monkeypatch.setattr(custom_host_pool, "replace", recording_replace)
    monkeypatch.setattr(custom_host_pool, "CompiledModel", recording_model)
    return trimmed
