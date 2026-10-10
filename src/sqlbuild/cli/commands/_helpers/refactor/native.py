"""Plan, stage, migrate and commit one refactoring with the native refactoring stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.cli.commands._helpers.refactor.facts import (
    declaration_moves_host,
    model_facts_json,
    refactor_facts_json,
)
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.refactoring.exceptions import (
    RefactorEditError,
    RefactorInputError,
    RefactorIOError,
    RefactorValueError,
    RefactorWriteError,
)
from sqlbuild.compiler.refactoring.models import (
    FileChange,
    ManualLocation,
    MigrationDeclaration,
    RefactorPlan,
    RefactorProject,
    RefactorRequest,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import (
    EditKind,
    NativeRefactorErrorKind,
    RefactorOperation,
)

_PLANNED_EDITS_KIND: str = "planned_edits"
_MIGRATION_EDITS_KIND: str = "migration_edits"
_PLAN_KEY: str = "plan"
_ERROR_KEY: str = "error"


def plan_native_refactor(
    *, project: RefactorProject, request: RefactorRequest
) -> tuple[RefactorPlan, str] | None:
    """Plan natively and count its edits, or return None where the Python planner must run."""

    response: dict[str, Any] = _response(
        cast(Any, _native).plan_refactor_json(
            refactor_facts_json(project=project, request=request),
            json.dumps(_request_payload(request)),
            declaration_moves_host(project=project),
        )
    )
    if response.get(_ERROR_KEY, {}).get("kind") == NativeRefactorErrorKind.DEFERRED:
        report_native_fallback(site=NativeFallbackSite.REFACTOR_PLAN)
        return None
    payload: dict[str, Any] = _payload(response=response, key=_PLAN_KEY)
    plan: RefactorPlan = decode_plan(payload)
    report_native_answer(
        stage=NativeStage.REFACTORING,
        kind=_PLANNED_EDITS_KIND,
        units=sum(len(change.edits) for change in plan.changes),
    )
    return plan, json.dumps(payload)


def stage_native_refactor(
    *, project_dir: Path, staging_dir: Path, plan_json: str, copy_inputs: bool
) -> dict[str, str]:
    """Stage a native plan in the scratch copy and return the original texts."""

    response: dict[str, Any] = _response(
        cast(Any, _native).stage_refactor_plan_json(
            str(project_dir), str(staging_dir), plan_json, copy_inputs
        )
    )
    return {path: text for path, text in _payload(response=response, key="originals")}


def migrate_native_refactor(
    *,
    plan_json: str,
    before: RefactorProject,
    after: RefactorProject | None,
    originals: dict[str, str],
) -> tuple[RefactorPlan, str]:
    """Return the native plan with model `migrate_from` added whenever its relation moves."""

    before_json: str | None = model_facts_json(project=before)
    response: dict[str, Any] = _response(
        cast(Any, _native).with_model_migration_json(
            plan_json,
            before_json,
            model_facts_json(project=after),
            json.dumps(list(originals.items())),
        )
    )
    payload: dict[str, Any] = _payload(response=response, key=_PLAN_KEY)
    migrated: RefactorPlan = decode_plan(payload)
    added: int = sum(len(change.edits) for change in migrated.changes) - sum(
        len(change.edits) for change in decode_plan(json.loads(plan_json)).changes
    )
    report_native_answer(stage=NativeStage.REFACTORING, kind=_MIGRATION_EDITS_KIND, units=added)
    return migrated, json.dumps(payload)


def commit_native_refactor(*, project_dir: Path, originals: dict[str, str], plan_json: str) -> None:
    """Write a verified native plan into the project, restoring every file if a write fails."""

    _ = _payload(
        response=_response(
            cast(Any, _native).commit_refactor_plan_json(
                str(project_dir), json.dumps(list(originals.items())), plan_json
            )
        ),
        key="written",
    )


def decode_plan(payload: dict[str, Any]) -> RefactorPlan:
    """Return the plan dataclasses of one native plan payload."""

    request: dict[str, Any] = payload["request"]
    return RefactorPlan(
        request=RefactorRequest(
            operation=RefactorOperation(request["operation"]),
            model_name=request["model_name"],
            new_name=request["new_name"],
            column_name=request.get("column_name"),
            destination=request.get("destination"),
            cascade=bool(request.get("cascade")),
        ),
        changes=tuple(_change(item) for item in payload["changes"]),
        manual=tuple(_manual(item) for item in payload["manual"]),
        blocking=tuple(_manual(item) for item in payload["blocking"]),
        migrations=tuple(
            MigrationDeclaration(
                model_name=item["model_name"],
                declaration=item["declaration"],
                reason=item["reason"],
            )
            for item in payload["migrations"]
        ),
        renamed_columns=tuple(
            (str(model), str(old), str(new)) for model, old, new in payload["renamed_columns"]
        ),
        help=payload.get("help"),
    )


def _change(item: dict[str, Any]) -> FileChange:
    return FileChange(
        path=item["path"],
        original_path=item["original_path"],
        edits=tuple(_edit(edit) for edit in item["edits"]),
    )


def _edit(item: dict[str, Any]) -> TextEdit:
    return TextEdit(
        start=int(item["start"]),
        end=int(item["end"]),
        replacement=item["replacement"],
        kind=EditKind(item["kind"]),
        line=int(item["line"]),
        column=int(item["column"]),
        before=item["before"],
        after=item["after"],
    )


def _manual(item: dict[str, Any]) -> ManualLocation:
    return ManualLocation(
        path=item["path"], line=item.get("line"), column=item.get("column"), reason=item["reason"]
    )


def _request_payload(request: RefactorRequest) -> dict[str, object]:
    return {
        "operation": request.operation.value,
        "model_name": request.model_name,
        "new_name": request.new_name,
        "column_name": request.column_name,
        "destination": request.destination,
        "cascade": request.cascade,
    }


def _response(text: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(text))


def _payload(*, response: dict[str, Any], key: str) -> Any:
    error: dict[str, Any] | None = response.get(_ERROR_KEY)
    if error is None:
        return response[key]
    kind: NativeRefactorErrorKind = NativeRefactorErrorKind(str(error["kind"]))
    message: str = str(error["message"])
    if kind is NativeRefactorErrorKind.VALUE:
        raise RefactorValueError(message)
    if kind is NativeRefactorErrorKind.IO:
        raise RefactorIOError(message)
    if kind is NativeRefactorErrorKind.EDIT:
        raise RefactorEditError(message)
    if kind is NativeRefactorErrorKind.WRITE:
        raise RefactorWriteError(message, help=error.get("help"))
    raise RefactorInputError(message, code=str(error["code"]), help=error.get("help"))
