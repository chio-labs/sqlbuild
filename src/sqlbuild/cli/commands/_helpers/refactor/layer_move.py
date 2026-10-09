"""Suggest the one-step `sqb mv` when a rename fails only on the layer-folder rules."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path, PurePosixPath

from sqlbuild.cli.commands.constants import (
    CONTIGUOUS_LAYER_FOLDERS,
    FOLDER_PLACEHOLDER,
    LAYER_FOLDER_RULE_CODES,
    LAYER_FOLDERS,
    MODEL_NAME_LAYER_INDEX,
    MODEL_NAME_LAYER_SEPARATOR,
    MODEL_NAME_PART_COUNTS,
    PROJECT_DIR_OPTION,
    SQL_FILE_SUFFIX,
    WINDOWS_OS_NAME,
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
    os_name: str = os.name,
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
    new_layer: str | None = _name_layer(new_name)
    layer_folder: tuple[str, ...] | None = (
        LAYER_FOLDERS.get(new_layer) if new_layer is not None else None
    )
    mirrored: tuple[tuple[str, ...], tuple[str, ...]] | None = (
        _mirrored_folder(
            original_path=renamed.original_path,
            current_layer=_name_layer(plan.request.model_name),
            layer_folder=layer_folder,
        )
        if layer_folder is not None
        else None
    )
    folders: tuple[str, ...] = (
        (*mirrored[0], *mirrored[1])
        if mirrored is not None
        else (PurePosixPath(renamed.original_path).parts[0], FOLDER_PLACEHOLDER)
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
        layer_folder="/".join(layer_folder) if layer_folder is not None else None,
        command=command_line(arguments=arguments, os_name=os_name),
    )


def command_line(*, arguments: list[str], os_name: str) -> str:
    """Quote a command for the shell of the platform it is printed on."""

    if os_name == WINDOWS_OS_NAME:
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def _name_layer(name: str) -> str | None:
    """Return the layer segment of a name in the rule grammar, as the layer-folder rules read it."""

    parts: list[str] = name.split(MODEL_NAME_LAYER_SEPARATOR)
    return parts[MODEL_NAME_LAYER_INDEX] if len(parts) in MODEL_NAME_PART_COUNTS else None


def _mirrored_folder(
    *, original_path: str, current_layer: str | None, layer_folder: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Swap the current layer's own folder for the new one, keeping the folders around it."""

    candidates: tuple[tuple[str, ...], ...] = tuple(
        folder
        for folder in (
            LAYER_FOLDERS.get(current_layer or ""),
            CONTIGUOUS_LAYER_FOLDERS.get(current_layer or ""),
        )
        if folder is not None
    )
    parent: tuple[str, ...] = PurePosixPath(original_path).parent.parts
    for current in candidates:
        for start in range(1, len(parent)):
            if parent[start : start + len(current)] == current:
                return (*parent[:start], *layer_folder), parent[start + len(current) :]
    return None
