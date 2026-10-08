"""Suggest the one-step `sqb mv` when a rename fails only on the layer-folder rules."""

from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath

from sqlbuild.cli.commands.constants import (
    CURRENT_LAYER_FOLDERS,
    FOLDER_PLACEHOLDER,
    LAYER_FOLDER_RULE_CODES,
    LAYER_FOLDERS,
    MODEL_NAME_LAYER_INDEX,
    MODEL_NAME_LAYER_SEPARATOR,
    PROJECT_DIR_OPTION,
    SQL_FILE_SUFFIX,
)
from sqlbuild.cli.commands.models import LayerMoveSuggestion
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.refactoring.models import FileChange, RefactorPlan
from sqlbuild.compiler.refactoring.types import RefactorOperation


def layer_move_suggestion(
    *,
    plan: RefactorPlan,
    diagnostics: tuple[CompilerDiagnostic, ...],
    project_dir: Path | None,
) -> LayerMoveSuggestion | None:
    """Return the `sqb mv` that renames and moves in one step, or None for any other failure."""

    renamed: FileChange | None = next((change for change in plan.changes if change.moved), None)
    if (
        plan.request.operation != RefactorOperation.RENAME_MODEL
        or renamed is None
        or not diagnostics
        or any(
            diagnostic.code not in LAYER_FOLDER_RULE_CODES
            or diagnostic.path is None
            or diagnostic.path.as_posix() != renamed.path
            for diagnostic in diagnostics
        )
    ):
        return None
    new_name: str = plan.request.new_name
    name_parts: list[str] = new_name.split(MODEL_NAME_LAYER_SEPARATOR)
    layer_folder: tuple[str, ...] | None = (
        LAYER_FOLDERS.get(name_parts[MODEL_NAME_LAYER_INDEX])
        if len(name_parts) > MODEL_NAME_LAYER_INDEX
        else None
    )
    if layer_folder is None:
        return None
    mirrored: tuple[tuple[str, ...], tuple[str, ...]] | None = _mirrored_folder(
        original_path=renamed.original_path, layer_folder=layer_folder
    )
    folders: tuple[str, ...] = (
        (*mirrored[0], *mirrored[1]) if mirrored is not None else (FOLDER_PLACEHOLDER,)
    )
    arguments: list[str] = [
        "sqb",
        "mv",
        plan.request.model_name,
        "/".join((*folders, f"{new_name}{SQL_FILE_SUFFIX}")),
    ]
    if project_dir is not None:
        arguments.extend((PROJECT_DIR_OPTION, str(project_dir)))
    return LayerMoveSuggestion(
        new_name=new_name,
        folder="/".join(mirrored[0]) if mirrored is not None else None,
        layer_folder="/".join(layer_folder),
        command=shlex.join(arguments),
    )


def _mirrored_folder(
    *, original_path: str, layer_folder: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Return the new layer folder in place of the current one, and the sub-path kept below it."""

    parent: tuple[str, ...] = PurePosixPath(original_path).parent.parts
    for start in range(1, len(parent)):
        current: tuple[str, ...] | None = next(
            (
                candidate
                for candidate in CURRENT_LAYER_FOLDERS
                if parent[start : start + len(candidate)] == candidate
            ),
            None,
        )
        if current is not None:
            return (*parent[:start], *layer_folder), parent[start + len(current) :]
    return None
