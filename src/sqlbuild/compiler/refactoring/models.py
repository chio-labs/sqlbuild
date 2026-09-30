"""Immutable models for planned and applied project refactorings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from yaml.nodes import ScalarNode

from sqlbuild.compiler.compile.models import CompiledModel, ExpansionSpan
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.refactoring.types import (
    EditKind,
    HeaderTokenKind,
    OffsetLocator,
    RefactorOperation,
    ResourceColumns,
    SpanMapper,
    SqlFileRole,
)


@dataclass(frozen=True)
class RefactorProject:
    """Compiler facts of one project, as the refactoring planner reads them."""

    project_dir: Path
    graph: ProjectGraph
    discovered: DiscoveredProjectInputs


@dataclass(frozen=True)
class RefactorRequest:
    """One requested rename or move."""

    operation: RefactorOperation
    model_name: str
    new_name: str
    column_name: str | None = None
    destination: str | None = None
    cascade: bool = False


@dataclass(frozen=True)
class ModelTarget:
    """The model a request names, and the request with its name and destination resolved."""

    model: CompiledModel
    request: RefactorRequest
    source_path: str

    @property
    def destination(self) -> str:
        return self.request.destination or self.source_path


@dataclass(frozen=True)
class TextEdit:
    """One replacement in an authored file, in offsets of the file before any edit."""

    start: int
    end: int
    replacement: str
    kind: EditKind
    line: int
    column: int
    before: str
    after: str


@dataclass(frozen=True)
class FileChange:
    """Every edit to one file, and where the file lives afterwards."""

    path: str
    original_path: str
    edits: tuple[TextEdit, ...] = field(default_factory=tuple)

    @property
    def moved(self) -> bool:
        return self.path != self.original_path


@dataclass(frozen=True)
class ManualLocation:
    """A location a refactoring cannot rewrite safely."""

    path: str
    line: int | None
    column: int | None
    reason: str


@dataclass(frozen=True)
class MigrationDeclaration:
    """A migrate_from declaration the refactoring adds to keep history."""

    model_name: str
    declaration: str
    reason: str


@dataclass(frozen=True)
class RefactorPlan:
    """Every edit, manual location, and migration of one refactoring."""

    request: RefactorRequest
    changes: tuple[FileChange, ...] = field(default_factory=tuple)
    manual: tuple[ManualLocation, ...] = field(default_factory=tuple)
    blocking: tuple[ManualLocation, ...] = field(default_factory=tuple)
    migrations: tuple[MigrationDeclaration, ...] = field(default_factory=tuple)
    renamed_columns: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    help: str | None = None


@dataclass(frozen=True)
class RefactorParts:
    """Edits and findings from one planning step, merged into a plan at the end."""

    edits: tuple[tuple[str, TextEdit], ...] = field(default_factory=tuple)
    manual: tuple[ManualLocation, ...] = field(default_factory=tuple)
    blocking: tuple[ManualLocation, ...] = field(default_factory=tuple)
    migrations: tuple[MigrationDeclaration, ...] = field(default_factory=tuple)
    cascaded: tuple[str, ...] = field(default_factory=tuple)
    moves: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectSqlFile:
    """One authored SQL file and the role discovery gave it."""

    relative_path: str
    contents: str
    role: SqlFileRole


@dataclass(frozen=True)
class AuthoredBody:
    """One SQL body inside an authored non-model file."""

    path: str
    role: SqlFileRole
    contents: str
    start: int
    text: str


@dataclass(frozen=True)
class ResourceSite:
    """One `__ref`, `__source`, or `__seed` call written in authored SQL."""

    kind: str
    name: str
    start: int
    end: int
    name_start: int
    name_end: int


@dataclass(frozen=True)
class AnalysisSql:
    """SQL whose interpolation sites were replaced by same-length identifiers."""

    sql: str
    tables: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelBody:
    """A model's compiled query and how it maps onto the authored file."""

    relative_path: str
    contents: str
    body_start: int
    compiled_sql: str
    passes: tuple[tuple[ExpansionSpan, ...], ...]


@dataclass(frozen=True)
class HeaderToken:
    """One MODEL header token in file offsets, with its nesting depth."""

    kind: HeaderTokenKind
    value: str
    start: int
    end: int
    depth: int


@dataclass(frozen=True)
class RelationshipTokens:
    """The target and field value tokens of one relationships audit in a MODEL header."""

    target: HeaderToken | None
    field: HeaderToken | None
    called: bool


@dataclass(frozen=True)
class YamlRelationship:
    """The `to` and `field` scalars of one relationships audit in a YAML declaration."""

    target: ScalarNode | None
    field: ScalarNode | None


@dataclass(frozen=True)
class HeaderEntry:
    """One top-level `key value` entry of a MODEL header."""

    key: str
    tokens: tuple[HeaderToken, ...]


@dataclass(frozen=True)
class ColumnReference:
    """One column expression that resolves to the renamed column."""

    start: int
    end: int
    name_start: int
    name_end: int
    scope: str
    projected: bool
    alias: str | None
    alias_start: int | None
    alias_end: int | None


@dataclass(frozen=True)
class ColumnSite:
    """A scoped construct at an optional span."""

    scope: str
    start: int | None
    end: int | None


@dataclass(frozen=True)
class OutputColumn:
    """One projection that names the column in a requested output scope."""

    scope: str
    start: int | None
    end: int | None
    alias_start: int | None
    alias_end: int | None


@dataclass(frozen=True)
class ColumnFacts:
    """Every rename-relevant fact about one column in one SQL body."""

    parsed: bool
    references: tuple[ColumnReference, ...] = field(default_factory=tuple)
    stars: tuple[ColumnSite, ...] = field(default_factory=tuple)
    joins: tuple[ColumnSite, ...] = field(default_factory=tuple)
    unresolved: tuple[ColumnSite, ...] = field(default_factory=tuple)
    outputs: tuple[OutputColumn, ...] = field(default_factory=tuple)
    star_outputs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ColumnQuery:
    """Which column of which relations one analysis resolves."""

    column: str
    target_tables: frozenset[str]
    target_ctes: frozenset[str] = frozenset()
    output_scopes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class BodyContext:
    """Where one analysed SQL body lives, and how its offsets map onto the file."""

    path: str
    contents: str
    map_span: SpanMapper
    locate: OffsetLocator
    fallback_offset: int


@dataclass(frozen=True)
class BodyEdits:
    """Edits, manual locations, and root pass-throughs found in one SQL body."""

    edits: tuple[TextEdit, ...] = field(default_factory=tuple)
    manual: tuple[ManualLocation, ...] = field(default_factory=tuple)
    passes_through: bool = False


@dataclass(frozen=True)
class ColumnRenameContext:
    """Everything a column rename reads while it walks downstream models."""

    project: RefactorProject
    owner: CompiledModel
    dialect: str
    columns: ResourceColumns
    contents: dict[str, str]
    bodies: tuple[AuthoredBody, ...]
    yaml_files: tuple[ProjectSqlFile, ...]
    schema_files: tuple[ProjectSqlFile, ...]
    old: str
    new: str
    cascade: bool


@dataclass(frozen=True)
class ModelMigrationDecision:
    """Whether a model needs migrate_from, and why, or why none can be written."""

    needed: bool
    reason: str
    blocked: bool = False
