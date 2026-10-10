"""Work out which declaration files a model move takes along."""

from __future__ import annotations

from sqlbuild.compiler.refactoring._helpers.renames.model_planning import declaration_moves
from sqlbuild.compiler.refactoring.models import ManualLocation, RefactorProject


def plan_declaration_moves(
    *, project: RefactorProject, model_name: str, source_path: str, destination: str
) -> tuple[tuple[tuple[str, str], ...], tuple[ManualLocation, ...]]:
    """Return `(file moves, blockers)` for moving a model from `source_path` to `destination`."""

    return declaration_moves(
        project=project, model_name=model_name, source_path=source_path, destination=destination
    )
