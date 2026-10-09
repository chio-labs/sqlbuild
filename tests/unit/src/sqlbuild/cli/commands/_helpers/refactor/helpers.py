"""Refactor output test builders."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.refactoring.models import FileChange, RefactorPlan, RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation


def build_move_plan(*, changed_files: int) -> RefactorPlan:
    """Return a move plan that changes the given number of files."""

    return RefactorPlan(
        request=RefactorRequest(
            operation=RefactorOperation.MOVE_MODEL,
            model_name="orders",
            new_name="",
            destination="models/marts/orders.sql",
        ),
        changes=tuple(
            FileChange(
                path=f"models/orders_{index}.sql", original_path=f"models/orders_{index}.sql"
            )
            for index in range(changed_files)
        ),
    )


def build_rename_plan(*, old_path: str, new_name: str) -> RefactorPlan:
    """Return a model rename plan whose file keeps its folder."""

    return RefactorPlan(
        request=RefactorRequest(
            operation=RefactorOperation.RENAME_MODEL,
            model_name=PurePosixPath(old_path).stem,
            new_name=new_name,
        ),
        changes=(
            FileChange(
                path=PurePosixPath(old_path).with_name(f"{new_name}.sql").as_posix(),
                original_path=old_path,
            ),
        ),
    )


def rule_diagnostics(*, codes: tuple[str, ...], path: str) -> tuple[CompilerDiagnostic, ...]:
    """Return one compile error per rule code, reported on `path`."""

    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILE,
            severity=DiagnosticSeverity.ERROR,
            code=code,
            message=f"{code} failed",
            path=Path(path),
        )
        for code in codes
    )
