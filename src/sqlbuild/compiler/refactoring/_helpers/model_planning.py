"""Resolve a model rename or move and find everything that blocks it."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.refactoring._helpers.header_edits import header_tokens, is_value
from sqlbuild.compiler.refactoring._helpers.model_references import (
    macro_reference_locations,
    model_reference_edits,
)
from sqlbuild.compiler.refactoring._helpers.project_files import (
    project_sql_files,
    python_string_locations,
)
from sqlbuild.compiler.refactoring._helpers.text_edits import manual_at
from sqlbuild.compiler.refactoring.constants import (
    GENERIC_DIALECT,
    IDENTIFIER_PATTERN,
    MIGRATE_FROM_KEY,
    MODEL_KIND_PREFIX,
    PATH_SEPARATOR,
    SQL_SUFFIX,
)
from sqlbuild.compiler.refactoring.exceptions import RefactorInputError
from sqlbuild.compiler.refactoring.models import (
    HeaderToken,
    ManualLocation,
    ModelTarget,
    ProjectSqlFile,
    RefactorParts,
    RefactorProject,
    RefactorRequest,
)
from sqlbuild.compiler.refactoring.types import RefactorOperation
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main.preview_scope_move import preview_scope_move
from sqlbuild.compiler.scopes.models import DeclarationReport, MovePreview, ScopeDiagnostic


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
    return RefactorParts(
        edits=model_reference_edits(files=files, old=old, new=new, dialect=dialect)
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
            *_scope_losses(project=project, target=target),
            *_pending_migration(files=files, target=target),
        ),
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


def _scope_losses(*, project: RefactorProject, target: ModelTarget) -> tuple[ManualLocation, ...]:
    if PurePosixPath(target.destination).parent == PurePosixPath(target.source_path).parent:
        return ()
    move: MovePreview | None
    diagnostics: tuple[ScopeDiagnostic, ...]
    move, diagnostics = preview_scope_move(
        lookup=build_scope_lookup(index=project.graph.project.scope_index),
        resource=f"{MODEL_KIND_PREFIX}{target.model.name}",
        destination=target.destination,
    )
    if move is None:
        return tuple(
            ManualLocation(path=target.destination, line=None, column=None, reason=item.message)
            for item in diagnostics
        ) or (
            ManualLocation(
                path=target.destination,
                line=None,
                column=None,
                reason="declaration scopes at the destination could not be checked",
            ),
        )
    lost: dict[str, DeclarationReport] = {report.identity: report for report in move.lost}
    return tuple(
        _scope_loss(identity=identity, report=lost.get(identity), target=target)
        for identity in move.invalidated_usages
    )


def _scope_loss(
    *, identity: str, report: DeclarationReport | None, target: ModelTarget
) -> ManualLocation:
    reason: str = (
        f"{identity} used by model:{target.model.name} is not visible from {target.destination}"
    )
    if report is None:
        return ManualLocation(path=target.source_path, line=None, column=None, reason=reason)
    return ManualLocation(
        path=report.definition.path,
        line=report.definition.line,
        column=report.definition.column,
        reason=reason,
    )


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
