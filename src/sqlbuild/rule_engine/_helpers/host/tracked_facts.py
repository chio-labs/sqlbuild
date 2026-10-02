"""Custom-rule fact views that record which compiler facts each evaluation reads."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledSqlTest, InferredColumn
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.rule_engine._helpers.engine.fact_replay import fact_error_digest, fact_value_digest
from sqlbuild.rule_engine.classes.fact_reads import FactReads
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
from sqlbuild.rule_engine.exceptions import FactDigestError
from sqlbuild.rule_engine.models import Model, ModelSql, ProjectPath, RuleFactViews


class _TrackedView:
    """Delegate unknown attribute access to the wrapped view and mark the evaluation uncacheable."""

    __slots__ = ("_tracked_reads", "_tracked_view")

    _tracked_reads: FactReads
    _tracked_view: Any

    def __init__(self, *, view: object, reads: FactReads) -> None:
        object.__setattr__(self, "_tracked_view", view)
        object.__setattr__(self, "_tracked_reads", reads)

    def __getattr__(self, name: str) -> object:
        self._tracked_reads.uncacheable = True
        return getattr(self._tracked_view, name)

    def __setattr__(self, name: str, value: object) -> None:
        self._tracked_reads.uncacheable = True
        setattr(self._tracked_view, name, value)


class _TrackedProjectTree(_TrackedView):
    """Record live filesystem reads with the digest of the value each read returned."""

    __slots__ = ()

    def paths(self) -> tuple[ProjectPath, ...]:
        key: tuple[str, ...] = (FACT_TREE_PATHS,)
        self._tracked_reads.record(key=key)
        observed: tuple[str, ...] | None = key if self._tracked_reads.current is not None else None
        return self._observed(key=observed, read=self._tracked_view.paths)

    def children(self, path: str = "") -> tuple[ProjectPath, ...]:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_CHILDREN, values=(path,)
        )
        return self._observed(key=key, read=lambda: self._tracked_view.children(path))

    def descendants(self, path: str = "") -> tuple[ProjectPath, ...]:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_DESCENDANTS, values=(path,)
        )
        return self._observed(key=key, read=lambda: self._tracked_view.descendants(path))

    def glob(self, pattern: str) -> tuple[ProjectPath, ...]:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_GLOB, values=(pattern,)
        )
        return self._observed(key=key, read=lambda: self._tracked_view.glob(pattern))

    def relative_parts(self, *, path: Path | str, under: str = "") -> tuple[str, ...]:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_RELATIVE_PARTS, values=(path, under)
        )
        return self._observed(
            key=key, read=lambda: self._tracked_view.relative_parts(path=path, under=under)
        )

    def resources_under(self, path: str) -> tuple[Model, ...]:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_RESOURCES_UNDER, values=(path,)
        )
        return self._observed(key=key, read=lambda: self._tracked_view.resources_under(path))

    def read_text(self, path: str) -> str:
        key: tuple[str, ...] | None = self._tracked_reads.record_text(
            fact=FACT_TREE_READ_TEXT, values=(path,)
        )
        return self._observed(key=key, read=lambda: self._tracked_view.read_text(path))

    def _observed[T](self, *, key: tuple[str, ...] | None, read: Callable[[], T]) -> T:
        reads: FactReads = self._tracked_reads
        if key is None or (key[0] != FACT_TREE_READ_TEXT and key in reads.observed):
            return read()
        try:
            value: T = read()
        except Exception as error:
            reads.observe(key=key, digest=_digest_or_none(error=error))
            raise
        reads.observe(key=key, digest=_digest_or_none(value=value))
        return value


def _digest_or_none(*, value: object = None, error: Exception | None = None) -> str | None:
    try:
        return fact_value_digest(value) if error is None else fact_error_digest(error)
    except FactDigestError:
        return None


class _TrackedProjectFacts(_TrackedView):
    __slots__ = ("_tracked_tree",)

    _tracked_tree: _TrackedProjectTree

    def __init__(self, *, view: object, reads: FactReads) -> None:
        super().__init__(view=view, reads=reads)
        object.__setattr__(
            self, "_tracked_tree", _TrackedProjectTree(view=self._tracked_view.tree, reads=reads)
        )

    @property
    def models(self) -> tuple[Model, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_MODELS,))
        return self._tracked_view.models

    @property
    def sources(self) -> tuple[object, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_SOURCES,))
        return self._tracked_view.sources

    @property
    def seeds(self) -> tuple[object, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_SEEDS,))
        return self._tracked_view.seeds

    @property
    def functions(self) -> tuple[object, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_FUNCTIONS,))
        return self._tracked_view.functions

    @property
    def tests(self) -> tuple[object, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_TESTS,))
        return self._tracked_view.tests

    @property
    def audits(self) -> tuple[object, ...]:
        self._tracked_reads.record(key=(FACT_PROJECT_AUDITS,))
        return self._tracked_view.audits

    @property
    def tree(self) -> _TrackedProjectTree:
        return self._tracked_tree


class _TrackedSqlFacts(_TrackedView):
    __slots__ = ()

    def for_model(self, model: Model) -> ModelSql:
        self._tracked_reads.record_model_path(fact=FACT_SQL_FOR_MODEL, model=model)
        return self._tracked_view.for_model(model)


class _TrackedGraphFacts(_TrackedView):
    __slots__ = ()

    def dependencies(self, model: Model) -> tuple[Model, ...]:
        self._tracked_reads.record_model_path(fact=FACT_GRAPH_DEPENDENCIES, model=model)
        return self._tracked_view.dependencies(model)

    def dependents(self, model: Model) -> tuple[Model, ...]:
        self._tracked_reads.record_model_path(fact=FACT_GRAPH_DEPENDENTS, model=model)
        return self._tracked_view.dependents(model)


class _TrackedColumnFacts(_TrackedView):
    __slots__ = ()

    def declared(self, model: Model) -> tuple[object, ...]:
        self._tracked_reads.record_model_path(fact=FACT_COLUMNS_DECLARED, model=model)
        return self._tracked_view.declared(model)

    def inferred(self, model: Model) -> tuple[InferredColumn, ...] | None:
        self._tracked_reads.record_model_path(fact=FACT_COLUMNS_INFERRED, model=model)
        return self._tracked_view.inferred(model)

    def names(self, model: Model) -> tuple[str, ...] | None:
        self._tracked_reads.record_model_path(fact=FACT_COLUMNS_NAMES, model=model)
        return self._tracked_view.names(model)


class _TrackedContractFacts(_TrackedView):
    __slots__ = ()

    def enforced(self, model: Model) -> bool:
        self._tracked_reads.record_model_path(fact=FACT_CONTRACTS_ENFORCED, model=model)
        return self._tracked_view.enforced(model)

    def grain(self, model: Model) -> tuple[str, ...]:
        self._tracked_reads.record_model_path(fact=FACT_CONTRACTS_GRAIN, model=model)
        return self._tracked_view.grain(model)


class _TrackedTestFacts(_TrackedView):
    __slots__ = ()

    def all(self) -> tuple[CompiledSqlTest, ...]:
        self._tracked_reads.record(key=(FACT_TESTS_ALL,))
        return self._tracked_view.all()

    def for_model(self, model: Model) -> tuple[CompiledSqlTest, ...]:
        self._tracked_reads.record_model_name(fact=FACT_TESTS_FOR_MODEL, model=model)
        return self._tracked_view.for_model(model)


class _TrackedAuditFacts(_TrackedView):
    __slots__ = ()

    def all(self) -> tuple[CompiledAudit, ...]:
        self._tracked_reads.record(key=(FACT_AUDITS_ALL,))
        return self._tracked_view.all()

    def for_model(self, model: Model) -> tuple[CompiledAudit, ...]:
        self._tracked_reads.record_model_name(fact=FACT_AUDITS_FOR_MODEL, model=model)
        return self._tracked_view.for_model(model)


class _TrackedDeclarationFacts(_TrackedView):
    __slots__ = ()

    @property
    def public_enums(self) -> tuple[EnumDeclaration, ...]:
        self._tracked_reads.record(key=(FACT_DECLARATIONS_PUBLIC_ENUMS,))
        return self._tracked_view.public_enums

    @property
    def public_constants(self) -> tuple[ConstantDeclaration, ...]:
        self._tracked_reads.record(key=(FACT_DECLARATIONS_PUBLIC_CONSTANTS,))
        return self._tracked_view.public_constants

    @property
    def enums(self) -> tuple[EnumDeclaration, ...]:
        self._tracked_reads.record(key=(FACT_DECLARATIONS_ENUMS,))
        return self._tracked_view.enums

    @property
    def constants(self) -> tuple[ConstantDeclaration, ...]:
        self._tracked_reads.record(key=(FACT_DECLARATIONS_CONSTANTS,))
        return self._tracked_view.constants


def tracked_fact_views(*, views: RuleFactViews, reads: FactReads) -> RuleFactViews:
    """Wrap every public fact view so reads are attributed to the active evaluation."""

    return RuleFactViews(
        project=_TrackedProjectFacts(view=views.project, reads=reads),
        sql=_TrackedSqlFacts(view=views.sql, reads=reads),
        graph=_TrackedGraphFacts(view=views.graph, reads=reads),
        columns=_TrackedColumnFacts(view=views.columns, reads=reads),
        contracts=_TrackedContractFacts(view=views.contracts, reads=reads),
        tests=_TrackedTestFacts(view=views.tests, reads=reads),
        audits=_TrackedAuditFacts(view=views.audits, reads=reads),
        declarations=_TrackedDeclarationFacts(view=views.declarations, reads=reads),
    )
