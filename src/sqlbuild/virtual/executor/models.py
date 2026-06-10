"""Virtual executor result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.shared.types import ExecutionResourceKind


@dataclass(frozen=True)
class VirtualBuildExecutionHooks:
    """Callbacks to use once a virtual build plan is ready."""

    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None
    on_node_complete: Callable[[object], None] | None = None
    on_sub_progress: Callable[[str], None] | None = None


@dataclass(frozen=True)
class VirtualBuildPipelineResult:
    """Result returned by the virtual build pipeline."""

    project: CompiledProject
    direct_plan_output: PlanOutput
    display_plan_output: PlanOutput
    execution_plan: PlanOutput
    execution_result: BuildExecutionResult
    python_node_results: tuple[PythonNodeExecutionResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualCloneItemResult:
    """One virtual clone hydration result."""

    model_name: str
    version_hash: str
    action: str
    message: str | None = None


@dataclass(frozen=True)
class VirtualCloneResult:
    """Result returned by virtual physical-version hydration."""

    mode: str
    origin_environment: str
    destination_environment: str
    destination_virtual_environment: str | None = None
    item_results: tuple[VirtualCloneItemResult, ...] = field(default_factory=tuple)

    @property
    def selected_count(self) -> int:
        return len(self.item_results)

    @property
    def found_count(self) -> int:
        return sum(1 for item in self.item_results if item.action in {"hydrated", "reused"})

    @property
    def hydrated_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "hydrated")

    @property
    def reused_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "reused")

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "missing")

    @property
    def skipped_locked_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "skipped_locked")
