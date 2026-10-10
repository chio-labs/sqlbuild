"""Refactor output test builders."""

from __future__ import annotations

import ast
from itertools import compress
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


def modules_importing(*, package_dir: Path, name: str) -> list[str]:
    """Return the sorted file names of the package's modules that import `name`."""

    paths: list[Path] = sorted(package_dir.glob("*.py"))
    flags: list[bool] = [_imports(path=path, name=name) for path in paths]
    return [path.name for path in compress(paths, flags)]


def _imports(*, path: Path, name: str) -> bool:
    tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[tuple[type[ast.AST], object]] = {
        (type(node), getattr(node, "name", None)) for node in ast.walk(tree)
    }
    return (ast.alias, name) in imported
