from dataclasses import dataclass, field

from sqlbuild.executor.build.models import BuildExecutionResult
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import ModelPlanOverride


@dataclass(frozen=True)
class BuildOutputTestCase:
    """Test case for build output formatting."""

    description: str
    result: BuildExecutionResult
    expected_output_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = field(default_factory=tuple)
    model_plan_overrides: tuple[ModelPlanOverride, ...] = field(default_factory=tuple)
    target: str | None = None
    concurrency: int = 1
    elapsed_seconds: float = 1.5
    verbose: bool = False
