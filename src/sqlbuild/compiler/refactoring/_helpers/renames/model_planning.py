"""Resolve a model rename or move, find what blocks it, and decide its migrations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.refactoring._helpers.project.project_files import (
    project_sql_files,
    python_string_locations,
    yaml_files,
)
from sqlbuild.compiler.refactoring._helpers.renames.model_references import (
    macro_reference_locations,
    model_reference_edits,
)
from sqlbuild.compiler.refactoring._helpers.text.header_edits import header_tokens, is_value
from sqlbuild.compiler.refactoring._helpers.text.text_edits import manual_at
from sqlbuild.compiler.refactoring._helpers.text.yaml_edits import yaml_model_edits
from sqlbuild.compiler.refactoring.constants import (
    GENERIC_DIALECT,
    HISTORY_MATERIALIZATIONS,
    IDENTIFIER_PATTERN,
    MATERIALIZED_KEY,
    MIGRATABLE_MATERIALIZATIONS,
    MIGRATE_FROM_KEY,
    MODEL_KIND_PREFIX,
    PATH_SEPARATOR,
    SQL_SUFFIX,
)
from sqlbuild.compiler.refactoring.exceptions import RefactorInputError
from sqlbuild.compiler.refactoring.models import (
    HeaderToken,
    ManualLocation,
    ModelMigrationDecision,
    ModelTarget,
    ProjectSqlFile,
    RefactorParts,
    RefactorProject,
    RefactorRequest,
)
from sqlbuild.compiler.refactoring.types import RefactorOperation
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main.preview_scope_move import preview_scope_move
from sqlbuild.compiler.scopes.main.relocate_declarations_for_move import (
    relocate_declarations_for_move,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    MovePreview,
    ResourceIdentity,
    ScopeDiagnostic,
    ScopeIndex,
)
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


def find_model(*, project: CompiledProject, name: str) -> CompiledModel:
    """Return the compiled model a kind-qualified target names."""

    model: CompiledModel | None = next((item for item in project.models if item.name == name), None)
    if model is None:
        raise RefactorInputError(
            f"{MODEL_KIND_PREFIX}{name} is not a model in this project",
            code="C951",
            help="list models with sqb dag --json or sqb scope --browse models",
        )
    return model


def validate_identifier(*, name: str, noun: str) -> None:
    """Refuse a new name that is not a plain SQL identifier."""

    if not IDENTIFIER_PATTERN.match(name):
        raise RefactorInputError(
            f"'{name}' is not a valid {noun} name",
            code="C952",
            help="use letters, digits, and underscores, starting with a letter or underscore",
        )


def model_target(*, project: RefactorProject, request: RefactorRequest) -> ModelTarget:
    """Resolve the model, its new name, and its destination file."""

    model: CompiledModel = find_model(project=project.graph.project, name=request.model_name)
    source_path: str = model.relative_path.as_posix()
    destination: str = (
        _resolve_destination(
            project_dir=project.project_dir,
            raw=request.destination or "",
            file_name=model.relative_path.name,
        )
        if request.operation == RefactorOperation.MOVE_MODEL
        else PurePosixPath(source_path).with_name(f"{request.new_name}{SQL_SUFFIX}").as_posix()
    )
    new: str = (
        PurePosixPath(destination).stem
        if request.operation == RefactorOperation.MOVE_MODEL
        else request.new_name
    )
    validate_identifier(name=new, noun="model")
    if new == model.name and destination == source_path:
        raise RefactorInputError(
            f"model:{model.name} already has that name and location", code="C953"
        )
    return ModelTarget(
        model=model,
        request=replace(request, new_name=new, destination=destination),
        source_path=source_path,
    )


def model_parts(*, project: RefactorProject, target: ModelTarget) -> RefactorParts:
    """Return every edit, manual location, and blocker of one model rename or move."""

    files: tuple[ProjectSqlFile, ...] = project_sql_files(discovered=project.discovered)
    dialect: str = project.graph.project.sql_analysis_dialect or GENERIC_DIALECT
    old: str = target.model.name
    new: str = target.request.new_name
    moves: tuple[tuple[str, str], ...]
    move_blockers: tuple[ManualLocation, ...]
    moves, move_blockers = _declaration_moves(project=project, target=target)
    return RefactorParts(
        edits=(
            *model_reference_edits(files=files, old=old, new=new, dialect=dialect),
            *yaml_model_edits(files=yaml_files(discovered=project.discovered), old=old, new=new),
        )
        if new != old
        else (),
        manual=(
            *macro_reference_locations(project=project, files=files, old=old, dialect=dialect),
            *python_string_locations(
                project_dir=project.project_dir,
                discovered=project.discovered,
                names=(old,),
                reason=f"Python code names model {old}; update it by hand",
            ),
        ),
        blocking=(
            *_collisions(project=project, target=target),
            *move_blockers,
            *_pending_migration(files=files, target=target),
        ),
        moves=moves,
    )


def _resolve_destination(*, project_dir: Path, raw: str, file_name: str) -> str:
    path: Path = Path(raw)
    absolute: Path = path if path.is_absolute() else project_dir / path
    if raw.endswith(PATH_SEPARATOR) or absolute.is_dir():
        absolute = absolute / file_name
    resolved: Path = absolute.resolve()
    if not resolved.is_relative_to(project_dir):
        raise RefactorInputError(f"destination '{raw}' is outside the project", code="C955")
    if resolved.suffix != SQL_SUFFIX:
        raise RefactorInputError(
            f"destination '{raw}' must be a .sql file or a folder ending in /", code="C955"
        )
    return resolved.relative_to(project_dir).as_posix()


def _collisions(*, project: RefactorProject, target: ModelTarget) -> tuple[ManualLocation, ...]:
    new: str = target.request.new_name
    found: list[ManualLocation] = [
        ManualLocation(
            path=other.relative_path.as_posix(),
            line=None,
            column=None,
            reason=f"model:{new} already exists",
        )
        for other in project.graph.project.models
        if other.name.lower() == new.lower() and other.name != target.model.name
    ]
    if (
        target.destination != target.source_path
        and (project.project_dir / PurePosixPath(target.destination)).exists()
    ):
        found.append(
            ManualLocation(
                path=target.destination,
                line=None,
                column=None,
                reason="destination file already exists",
            )
        )
    return tuple(found)


def _declaration_moves(
    *, project: RefactorProject, target: ModelTarget
) -> tuple[tuple[tuple[str, str], ...], tuple[ManualLocation, ...]]:
    """Move the declarations the model uses to where placement requires them afterwards."""

    if PurePosixPath(target.destination).parent == PurePosixPath(target.source_path).parent:
        return (), ()
    index: ScopeIndex = project.graph.project.scope_index
    move: MovePreview | None
    diagnostics: tuple[ScopeDiagnostic, ...]
    move, diagnostics = preview_scope_move(
        lookup=build_scope_lookup(index=index),
        resource=f"{MODEL_KIND_PREFIX}{target.model.name}",
        destination=target.destination,
    )
    relocated: tuple[DeclarationRecord, ...] | None = (
        None
        if move is None
        else relocate_declarations_for_move(
            index=index,
            resource=ResourceIdentity(kind=ResourceKind.MODEL, name=target.model.name),
            destination=target.destination,
        )
    )
    if move is None or relocated is None:
        return (), tuple(
            ManualLocation(path=target.destination, line=None, column=None, reason=item.message)
            for item in diagnostics
        ) or (
            ManualLocation(
                path=target.destination,
                line=None,
                column=None,
                reason="declaration placement at the destination could not be worked out",
            ),
        )
    return _file_moves(project=project, index=index, relocated=relocated)


def _file_moves(
    *, project: RefactorProject, index: ScopeIndex, relocated: tuple[DeclarationRecord, ...]
) -> tuple[tuple[tuple[str, str], ...], tuple[ManualLocation, ...]]:
    destinations: dict[str, str] = {}
    blocking: list[ManualLocation] = []
    record: DeclarationRecord
    for record in sorted(relocated, key=lambda item: item.identity):
        original: DeclarationRecord = next(
            item for item in index.declarations if item.identity == record.identity
        )
        label: str = _label(record.identity)
        if not (project.project_dir / PurePosixPath(original.path)).is_file():
            blocking.append(
                _declaration_blocker(
                    record=original,
                    reason=f"{label} must move to {record.path}, but it is not an authored "
                    "project file",
                )
            )
            continue
        planned: str | None = destinations.setdefault(original.path, record.path)
        if planned != record.path:
            blocking.append(
                _declaration_blocker(
                    record=original,
                    reason=f"{original.path} holds declarations that must move to different "
                    f"folders ({planned}, {record.path}); split the file first",
                )
            )
    moving: frozenset[DeclarationIdentity] = frozenset(item.identity for item in relocated)
    staying: DeclarationRecord
    for staying in index.declarations:
        if staying.path in destinations and staying.identity not in moving:
            blocking.append(
                _declaration_blocker(
                    record=staying,
                    reason=f"{destinations[staying.path]} would take "
                    f"{_label(staying.identity)} along, which must "
                    f"stay in {staying.path}; split the file first",
                )
            )
    new_path: str
    for new_path in sorted(set(destinations.values())):
        if (project.project_dir / PurePosixPath(new_path)).exists():
            blocking.append(
                ManualLocation(
                    path=new_path,
                    line=None,
                    column=None,
                    reason="a declaration must move here, but the file already exists",
                )
            )
    return tuple(sorted(destinations.items())), tuple(blocking)


def _label(identity: DeclarationIdentity) -> str:
    return f"{identity.kind.value}:{identity.name}"


def _declaration_blocker(*, record: DeclarationRecord, reason: str) -> ManualLocation:
    return ManualLocation(path=record.path, line=record.line, column=record.column, reason=reason)


def _pending_migration(
    *, files: tuple[ProjectSqlFile, ...], target: ModelTarget
) -> tuple[ManualLocation, ...]:
    if MIGRATE_FROM_KEY not in target.model.config.values:
        return ()
    contents: str = next(
        (item.contents for item in files if item.relative_path == target.source_path), ""
    )
    token: HeaderToken | None = next(
        (
            item
            for item in header_tokens(contents=contents) or ()
            if item.depth == 0 and is_value(token=item, value=MIGRATE_FROM_KEY)
        ),
        None,
    )
    return (
        manual_at(
            path=target.source_path,
            text=contents,
            offset=token.start if token is not None else None,
            reason=(
                f"model:{target.model.name} still declares migrate_from; build it on every "
                "target and remove migrate_from before renaming it again"
            ),
        ),
    )


def decide_model_migration(
    *, before: CompiledProject, after: CompiledProject | None, old: str, new: str
) -> ModelMigrationDecision:
    """Declare migrate_from whenever the relation moves, unless migrations cannot follow it."""

    old_model: CompiledModel | None = _model(project=before, name=old)
    new_model: CompiledModel | None = None if after is None else _model(project=after, name=new)
    if old_model is None:
        return ModelMigrationDecision(needed=False, reason="model not compiled")
    materialized: str | None = get_config_str(
        values=(new_model or old_model).config.values, key=MATERIALIZED_KEY
    )
    if materialized not in MIGRATABLE_MATERIALIZATIONS:
        return ModelMigrationDecision(
            needed=False, reason=f"'{materialized}' models keep no warehouse data"
        )
    if after is None or new_model is None:
        return ModelMigrationDecision(
            needed=True,
            reason="keeps the relation's history; the destination could not be checked because "
            "the edited project does not compile",
        )
    if _location_key(old_model) == _location_key(new_model):
        return ModelMigrationDecision(needed=False, reason="relation name is unchanged")
    return _blocked_move(after=after, old_model=old_model, new_model=new_model) or (
        ModelMigrationDecision(
            needed=True, reason="keeps the relation's history and its old name working"
        )
    )


def _blocked_move(
    *, after: CompiledProject, old_model: CompiledModel, new_model: CompiledModel
) -> ModelMigrationDecision | None:
    old_database: str = (old_model.destination.database or "").lower()
    new_database: str = (new_model.destination.database or "").lower()
    if old_database and new_database and old_database != new_database:
        return ModelMigrationDecision(
            needed=False,
            blocked=True,
            reason=(
                f"moves from database {old_model.destination.database} to "
                f"{new_model.destination.database}; migrations cannot cross databases"
            ),
        )
    old_schema: str = (old_model.destination.schema or "").lower()
    project_schemas: frozenset[str] = frozenset(
        (model.destination.schema or "").lower() for model in after.models
    )
    if old_schema in project_schemas:
        return None
    return ModelMigrationDecision(
        needed=False,
        blocked=True,
        reason=(
            f"no model is left in schema {old_model.destination.schema}, so migrate_from "
            f"{old_model.name} cannot find the old relation; add a schema-qualified "
            "migrate_from for each target"
        ),
    )


def needs_column_migration(*, model: CompiledModel) -> bool:
    """Return whether renaming a column of this model must declare migrate_from."""

    materialized: str | None = get_config_str(values=model.config.values, key=MATERIALIZED_KEY)
    if materialized in HISTORY_MATERIALIZATIONS:
        return True
    return (
        materialized in MIGRATABLE_MATERIALIZATIONS
        and model.config.values.get(MIGRATE_FROM_KEY) is not None
    )


def _model(*, project: CompiledProject, name: str) -> CompiledModel | None:
    return next((model for model in project.models if model.name == name), None)


def _location_key(model: CompiledModel) -> tuple[str, str, str]:
    return (
        (model.destination.database or "").lower(),
        (model.destination.schema or "").lower(),
        model.destination.name.lower(),
    )
