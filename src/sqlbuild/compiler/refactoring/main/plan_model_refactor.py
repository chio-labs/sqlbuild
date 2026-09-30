"""Plan a model rename or move from compiler facts."""

from __future__ import annotations

from sqlbuild.compiler.refactoring._helpers.renames.model_planning import model_parts, model_target
from sqlbuild.compiler.refactoring._helpers.text.text_edits import build_plan
from sqlbuild.compiler.refactoring.constants import MODEL_MANUAL_HELP
from sqlbuild.compiler.refactoring.models import (
    ModelTarget,
    RefactorParts,
    RefactorPlan,
    RefactorProject,
    RefactorRequest,
)


def plan_model_refactor(*, project: RefactorProject, request: RefactorRequest) -> RefactorPlan:
    """Plan every edit that renames or moves one model, without touching files."""

    target: ModelTarget = model_target(project=project, request=request)
    parts: RefactorParts = model_parts(project=project, target=target)
    return build_plan(
        request=target.request,
        parts=parts,
        moves={
            **dict(parts.moves),
            **(
                {target.source_path: target.destination}
                if target.destination != target.source_path
                else {}
            ),
        },
        help=MODEL_MANUAL_HELP,
    )
