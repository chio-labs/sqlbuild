"""Index a compilation so two compilations can be compared file by file."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.lint.models import CompileFacts
from sqlbuild.lint.types import DiagnosticIdentity


def compile_facts(*, project: CompiledProject, project_dir: Path) -> CompileFacts:
    """Index a compilation so two compilations can be compared file by file."""

    model_paths: dict[CompiledObjectKey, Path] = {
        model.key: (project_dir / model.relative_path).resolve() for model in project.models
    }
    paths_by_name: dict[str, Path] = {
        model.name: model_paths[model.key] for model in project.models
    }
    diagnostics: dict[Path, Counter[DiagnosticIdentity]] = {}
    for diagnostic in project.diagnostics:
        owner: Path = _owner(
            diagnostic=diagnostic, paths_by_name=paths_by_name, project_dir=project_dir
        )
        diagnostics.setdefault(owner, Counter())[_identity(diagnostic)] += 1
    return CompileFacts(
        models={model.key: model for model in project.models},
        model_paths=model_paths,
        diagnostics=diagnostics,
    )


def _owner(
    *, diagnostic: CompilerDiagnostic, paths_by_name: dict[str, Path], project_dir: Path
) -> Path:
    if (
        diagnostic.resource_type == CompiledResourceType.MODEL
        and diagnostic.resource_name in paths_by_name
    ):
        return paths_by_name[diagnostic.resource_name]
    path: Path | None = diagnostic.path or (
        diagnostic.location.path if diagnostic.location is not None else None
    )
    return (project_dir / path).resolve() if path is not None else project_dir.resolve()


def _identity(diagnostic: CompilerDiagnostic) -> DiagnosticIdentity:
    """Location-insensitive identity, so moved lines do not count as new diagnostics."""

    return (
        diagnostic.code,
        str(diagnostic.resource_type or ""),
        diagnostic.resource_name or "",
        diagnostic.message,
    )
