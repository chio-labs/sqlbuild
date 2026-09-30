"""Human and JSON output for `sqb rename` and `sqb mv`."""

from __future__ import annotations

import json

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.refactoring.constants import OPERATION_TITLES
from sqlbuild.compiler.refactoring.models import (
    FileChange,
    ManualLocation,
    MigrationDeclaration,
    RefactorPlan,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import RefactorOperation, RefactorStatus
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.tree_connector import tree_connector

_CONTINUE: str = "\u2502   "
_BLANK: str = "    "
_POSITION_WIDTH: int = 8
_KIND_WIDTH: int = 10
_EXCERPT_LIMIT: int = 60


def render_refactor_text(
    *,
    plan: RefactorPlan,
    status: RefactorStatus,
    diagnostics: tuple[CompilerDiagnostic, ...],
    use_color: bool,
) -> str:
    """Render the edit tree, manual locations, and one terminal status line."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.title(_heading(plan))]
    blocked: bool = status == RefactorStatus.REFUSED
    if not blocked or not (plan.blocking or plan.manual):
        lines.extend(_change_lines(style=style, changes=plan.changes))
    if plan.migrations and not blocked:
        lines.append(style.section("Migrations"))
        lines.extend(_migration_lines(style=style, migrations=plan.migrations))
    if blocked:
        lines.append(style.error_strong(f"Cannot {_verb(plan)} {_target(plan)} automatically"))
        lines.extend(_location_lines(style=style, locations=(*plan.blocking, *plan.manual)))
        if plan.help and plan.manual:
            lines.append(plan.help)
    if diagnostics:
        lines.append(style.error_strong("Compile errors in the edited project"))
        lines.extend(_diagnostic_lines(style=style, diagnostics=diagnostics))
    lines.append(_status_line(style=style, plan=plan, status=status))
    return "\n".join(lines) + "\n"


def render_refactor_json(
    *,
    plan: RefactorPlan,
    status: RefactorStatus,
    diagnostics: tuple[CompilerDiagnostic, ...],
) -> str:
    """Render the same facts as stable JSON."""

    payload: dict[str, object] = {
        "operation": plan.request.operation.value,
        "target": _target(plan),
        "new_name": plan.request.new_name,
        "destination": plan.request.destination,
        "cascade": plan.request.cascade,
        "status": status.value,
        "files_changed": len(plan.changes) if status == RefactorStatus.APPLIED else 0,
        "files": [_file_payload(change) for change in plan.changes],
        "migrations": [
            {
                "model": migration.model_name,
                "declaration": migration.declaration,
                "reason": migration.reason,
            }
            for migration in plan.migrations
        ],
        "renamed_columns": [
            {"model": model, "from": old, "to": new} for model, old, new in plan.renamed_columns
        ],
        "manual": [_location_payload(item) for item in plan.manual],
        "blocking": [_location_payload(item) for item in plan.blocking],
        "compile": {
            "ok": not diagnostics,
            "errors": [
                {
                    "code": diagnostic.code,
                    "message": diagnostic.message,
                    "path": diagnostic.path.as_posix() if diagnostic.path is not None else None,
                    "line": diagnostic.line,
                }
                for diagnostic in diagnostics
            ],
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def _file_payload(change: FileChange) -> dict[str, object]:
    return {
        "path": change.path,
        "from_path": change.original_path if change.moved else None,
        "edits": [
            _edit_payload(edit) for edit in sorted(change.edits, key=lambda item: item.start)
        ],
    }


def _edit_payload(edit: TextEdit) -> dict[str, object]:
    return {
        "line": edit.line,
        "column": edit.column,
        "kind": edit.kind.value,
        "before": edit.before,
        "after": edit.after,
    }


def _heading(plan: RefactorPlan) -> str:
    title: str = OPERATION_TITLES[plan.request.operation]
    if plan.request.operation == RefactorOperation.RENAME_COLUMN:
        return (
            f"{title}  {plan.request.model_name}.{plan.request.column_name} -> "
            f"{plan.request.new_name}"
        )
    if plan.request.operation == RefactorOperation.MOVE_MODEL:
        return f"{title}  {plan.request.model_name} -> {plan.request.destination}"
    return f"{title}  {plan.request.model_name} -> {plan.request.new_name}"


def _verb(plan: RefactorPlan) -> str:
    return "move" if plan.request.operation == RefactorOperation.MOVE_MODEL else "rename"


def _target(plan: RefactorPlan) -> str:
    if plan.request.operation == RefactorOperation.RENAME_COLUMN:
        return f"column:{plan.request.model_name}.{plan.request.column_name}"
    return f"model:{plan.request.model_name}"


def _change_lines(*, style: CliStyle, changes: tuple[FileChange, ...]) -> list[str]:
    lines: list[str] = []
    index: int
    change: FileChange
    for index, change in enumerate(changes):
        last: bool = index == len(changes) - 1
        moved: str = style.muted(f"  (moved from {change.original_path})") if change.moved else ""
        lines.append(f"{tree_connector(style=style, last=last)} {change.path}{moved}")
        prefix: str = _BLANK if last else _CONTINUE
        edits: list[TextEdit] = sorted(change.edits, key=lambda item: item.start)
        edit_index: int
        edit: TextEdit
        for edit_index, edit in enumerate(edits):
            connector: str = tree_connector(style=style, last=edit_index == len(edits) - 1)
            position: str = f"{edit.line}:{edit.column}".ljust(_POSITION_WIDTH)
            lines.append(
                f"{style.muted(prefix)}{connector} {position}{edit.kind.value.ljust(_KIND_WIDTH)}"
                f"{_excerpt(edit.before)}  ->  {_excerpt(edit.after)}"
                if edit.before
                else f"{style.muted(prefix)}{connector} {position}"
                f"{edit.kind.value.ljust(_KIND_WIDTH)}+ {_excerpt(edit.after)}"
            )
    return lines


def _migration_lines(*, style: CliStyle, migrations: tuple[MigrationDeclaration, ...]) -> list[str]:
    return [
        f"{tree_connector(style=style, last=index == len(migrations) - 1)} "
        f"{style.object_name(item.model_name)}  {item.declaration}  {style.muted(item.reason)}"
        for index, item in enumerate(migrations)
    ]


def _location_lines(*, style: CliStyle, locations: tuple[ManualLocation, ...]) -> list[str]:
    return [
        f"{tree_connector(style=style, last=index == len(locations) - 1)} "
        f"{_position(item)}  {item.reason}"
        for index, item in enumerate(locations)
    ]


def _diagnostic_lines(*, style: CliStyle, diagnostics: tuple[CompilerDiagnostic, ...]) -> list[str]:
    return [
        f"{tree_connector(style=style, last=index == len(diagnostics) - 1)} "
        f"{diagnostic.code}  "
        + (
            f"{diagnostic.path.as_posix()}:{diagnostic.line or ''}  "
            if diagnostic.path is not None
            else ""
        )
        + diagnostic.message.splitlines()[0]
        for index, diagnostic in enumerate(diagnostics)
    ]


def _status_line(*, style: CliStyle, plan: RefactorPlan, status: RefactorStatus) -> str:
    count: int = len(plan.changes)
    files: str = f"{count} file{'s' if count != 1 else ''}"
    if status == RefactorStatus.APPLIED:
        return style.success_strong(f"Compiled: ok, {files} changed")
    if status == RefactorStatus.DRY_RUN:
        return style.success_strong(f"Dry run: compiles, {files} would change; nothing written")
    if status == RefactorStatus.COMPILE_FAILED:
        return style.error_strong("Compiled: failed; no files changed")
    return style.error_strong("Refused; no files changed")


def _position(location: ManualLocation) -> str:
    if location.line is None:
        return location.path
    return f"{location.path}:{location.line}:{location.column or 1}"


def _location_payload(location: ManualLocation) -> dict[str, object]:
    return {
        "path": location.path,
        "line": location.line,
        "column": location.column,
        "reason": location.reason,
    }


def _excerpt(text: str) -> str:
    single: str = " ".join(text.split())
    return single if len(single) <= _EXCERPT_LIMIT else single[: _EXCERPT_LIMIT - 1] + "\u2026"
