"""Virtual executor callback types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.models.core import CompiledProject
    from sqlbuild.compiler.pipeline.models import PythonPlanEntry
    from sqlbuild.compiler.planner.models import PlanOutput
    from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks


class VirtualPlanReadyCallback(Protocol):
    def __call__(
        self,
        project: CompiledProject,
        *,
        plan_output: PlanOutput,
        python_plan_entries: tuple[PythonPlanEntry, ...],
    ) -> VirtualBuildExecutionHooks: ...
